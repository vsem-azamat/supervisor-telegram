"""PydanticAI-based conversational review agent for editing Telegram channel posts.

Replaces the stateless single-LLM-call edit flow with a full conversational agent
that has tools and memory, enabling multi-turn editing sessions per post.
"""

import asyncio
import functools
import time
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.config import settings
from app.core.enums import PostStatus
from app.core.logging import get_logger

logger = get_logger("channel.review_agent")

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@dataclass
class ReviewAgentDeps:
    """Dependencies injected into the review agent at each turn."""

    session_maker: Any  # async_sessionmaker[AsyncSession]
    bot: Any  # aiogram.Bot
    post_id: int
    channel_id: int
    channel_name: str
    channel_username: str | None
    footer: str
    review_chat_id: int | str


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------

_MAX_REVIEW_CONVERSATIONS = 200
_REVIEW_CONVERSATION_TTL = 14400  # 4 hours
_MAX_HISTORY = 40
_AGENT_TIMEOUT_SECONDS = 60


class ReviewConversationRegistry:
    """In-memory registry for per-post review conversations.

    Holds four pieces of state that must stay consistent: message history,
    last-access timestamps, Telegram-message → post-id lookup, and per-post
    asyncio locks. Eviction and cleanup update all four atomically, so
    callers don't have to remember the cross-cutting invariants.
    """

    def __init__(self, *, max_conversations: int = _MAX_REVIEW_CONVERSATIONS, ttl: int = _REVIEW_CONVERSATION_TTL):
        self._max_conversations = max_conversations
        self._ttl = ttl
        self._conversations: dict[int, list[ModelMessage]] = {}
        self._last_access: dict[int, float] = {}
        self._message_to_post: dict[int, int] = {}
        self._post_locks: dict[int, asyncio.Lock] = {}

    # ── History read/write ──

    def get_history(self, post_id: int) -> list[ModelMessage] | None:
        return self._conversations.get(post_id)

    def set_history(self, post_id: int, messages: list[ModelMessage]) -> None:
        self._conversations[post_id] = messages
        self._last_access[post_id] = time.monotonic()

    def history_length(self, post_id: int) -> int:
        return len(self._conversations.get(post_id) or [])

    # ── Telegram message ↔ post mapping ──

    def register_message(self, message_id: int, post_id: int) -> None:
        self._message_to_post[message_id] = post_id

    def resolve_post_id(self, message_id: int) -> int | None:
        return self._message_to_post.get(message_id)

    # ── Locks ──

    def get_post_lock(self, post_id: int) -> asyncio.Lock:
        if post_id not in self._post_locks:
            self._post_locks[post_id] = asyncio.Lock()
        return self._post_locks[post_id]

    # ── Cleanup ──

    def _forget(self, post_id: int) -> None:
        """Remove all state for a post. Keeps the four dicts consistent."""
        self._conversations.pop(post_id, None)
        self._last_access.pop(post_id, None)
        self._post_locks.pop(post_id, None)
        stale = [mid for mid, pid in self._message_to_post.items() if pid == post_id]
        for mid in stale:
            self._message_to_post.pop(mid, None)

    def clear(self, post_id: int) -> None:
        """Called on approve/reject/delete when the review session is done."""
        self._forget(post_id)
        logger.debug("review_conversation_cleared", post_id=post_id)

    def evict_stale(self) -> None:
        """Evict conversations idle for >TTL, then enforce max cap (LRU)."""
        now = time.monotonic()

        expired = [pid for pid, ts in self._last_access.items() if now - ts > self._ttl]
        for pid in expired:
            self._forget(pid)

        if len(self._conversations) > self._max_conversations:
            sorted_by_access = sorted(self._last_access.items(), key=lambda x: x[1])
            to_remove = len(self._conversations) - self._max_conversations
            for pid, _ in sorted_by_access[:to_remove]:
                self._forget(pid)


_registry = ReviewConversationRegistry()


# Public API kept as free functions (external callers don't touch the class).


def clear_review_conversation(post_id: int) -> None:
    """Clear conversation, lock, and message mappings for a post (call on approve/reject)."""
    _registry.clear(post_id)


def register_message(message_id: int, post_id: int) -> None:
    """Register a Telegram message_id as belonging to a post's conversation (in-memory)."""
    _registry.register_message(message_id, post_id)


def resolve_post_id(message_id: int) -> int | None:
    """Look up which post_id a Telegram message belongs to (in-memory only)."""
    return _registry.resolve_post_id(message_id)


_MAX_REPLY_CHAIN = 100  # cap per post to prevent unbounded growth


async def persist_message_to_db(session_maker: Any, post_id: int, message_id: int) -> None:
    """Persist a message_id → post_id mapping in the DB for restart resilience."""
    from sqlalchemy import select

    from app.db.models import ChannelPost

    try:
        async with session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()
            if not post:
                return
            chain: list[int] = list(post.reply_chain_message_ids or [])
            if message_id not in chain:
                chain.append(message_id)
                # Keep only the most recent entries
                if len(chain) > _MAX_REPLY_CHAIN:
                    chain = chain[-_MAX_REPLY_CHAIN:]
                post.reply_chain_message_ids = chain
                await session.commit()
    except Exception:
        logger.warning("persist_message_to_db_failed", post_id=post_id, message_id=message_id, exc_info=True)


async def clear_reply_chain_from_db(session_maker: Any, post_id: int) -> None:
    """Null out reply_chain_message_ids when a post is finalized (approve/reject/skip)."""
    from sqlalchemy import update

    from app.db.models import ChannelPost

    try:
        async with session_maker() as session:
            await session.execute(
                update(ChannelPost).where(ChannelPost.id == post_id).values(reply_chain_message_ids=None)
            )
            await session.commit()
    except Exception:
        logger.warning("clear_reply_chain_failed", post_id=post_id, exc_info=True)


async def resolve_post_id_from_db(session_maker: Any, message_id: int, chat_id: int) -> int | None:
    """Fallback: resolve post_id from DB when in-memory mapping is empty (e.g. after restart).

    Checks review_message_id first, then reply_chain_message_ids.
    Filters by chat_id and active statuses to avoid false matches.
    """
    from sqlalchemy import select

    from app.core.enums import PostStatus
    from app.db.models import ChannelPost

    active_statuses = [PostStatus.DRAFT, PostStatus.SCHEDULED]

    try:
        async with session_maker() as session:
            # 1. Direct hit: review_message_id
            result = await session.execute(
                select(ChannelPost.id)
                .where(ChannelPost.review_message_id == message_id)
                .where(ChannelPost.review_chat_id == chat_id)
                .where(ChannelPost.status.in_(active_statuses))
            )
            post_id = result.scalar_one_or_none()
            if post_id:
                return post_id

            # 2. Search reply_chain_message_ids (JSON array)
            result = await session.execute(
                select(ChannelPost.id, ChannelPost.reply_chain_message_ids)
                .where(ChannelPost.review_chat_id == chat_id)
                .where(ChannelPost.status.in_(active_statuses))
                .where(ChannelPost.reply_chain_message_ids.isnot(None))
            )
            for row_post_id, chain_ids in result.all():
                if chain_ids and message_id in chain_ids:
                    return row_post_id
    except Exception:
        logger.warning("resolve_post_id_from_db_failed", message_id=message_id, chat_id=chat_id, exc_info=True)

    return None


# ---------------------------------------------------------------------------
# Agent creation
# ---------------------------------------------------------------------------

_FOOTER_PLACEHOLDER = "{{FOOTER}}"

_SYSTEM_PROMPT_TEMPLATE = """\
You are a post editor for a Telegram channel. Your job is to edit posts \
according to admin instructions while maintaining the channel's style.

## Current channel footer
{{FOOTER}}

## Rules
- LENGTH: 300-500 chars for news, up to 700 for analysis. Hard limit 900 chars.
- TONE: Friendly, slightly witty — like a smart friend sharing news. \
Not too formal, not too casual.
  BAD: 'Уважаемые студенты! Администрация сообщает...'
  BAD: 'ааа братцы дедлайн продлили!!!'
  BAD (too pompous): 'Это отличная возможность лично расспросить экспертов!'
  GOOD: 'Если вы ещё не подали заявку — есть хорошая новость.'
  GOOD: 'На выставке будут стенды факультета — можно задать вопросы.'
- BANNED PHRASES (never use): "это отличная/уникальная/прекрасная возможность", \
"лично можете расспросить/узнать", "не упустите шанс", "спешите", "успейте", \
"рады сообщить", "с гордостью представляем". No ad/press-release/marketing tone.
- Use standard Markdown: **bold**, *italic*, [link](url). No HTML tags, no hashtags.
- Max 1 emoji (at headline start), max 1 exclamation mark per post.
- Always leave blank lines between headline, paragraphs, and footer.
- ALWAYS end the post with the channel footer shown above.

## CRITICAL Workflow — you MUST follow these steps every time
1. ALWAYS call `get_current_post` first to read the current text from DB.
2. Make edits based on the admin's instruction.
3. ALWAYS call `update_post` with the FULL edited text to save changes.
4. After `update_post` succeeds, briefly confirm what you changed.
5. If the admin asks to search for information, use `web_search`.

## MANDATORY: You MUST call tools
If the admin asks to edit, change, fix, shorten, rewrite, translate, or modify \
the post in ANY way, you MUST:
- Call `get_current_post` to read the current text
- Call `update_post` with the full new text to save it

If you do NOT call `update_post`, the post will NOT be changed — your edits are LOST. \
The system will detect if you skip the tool call and force a retry.

## Examples of CORRECT vs INCORRECT behavior

INCORRECT (DO NOT DO THIS):
  Admin: "сделай заголовок короче"
  You: "Готово! Сократил заголовок."
  ❌ WRONG — update_post was never called, nothing changed!

CORRECT:
  Admin: "сделай заголовок короче"
  You: [calls get_current_post] → [calls update_post with edited text] → "Сократил заголовок с 12 до 7 слов."
  ✅ RIGHT — tools were called, changes saved.

## Tools available
- `get_current_post` — read the current post text from DB (ALWAYS call first)
- `web_search` — search the web for facts or context
- `update_post` — save the edited text (MUST call to apply text changes)
- `list_images` — show current images and the candidate pool with scores
- `use_candidate` — promote a pooled candidate to the post
- `add_image_url` — add an external URL (validated before accepting)
- `find_and_add_image` — search Brave Images, add best result to the pool
- `remove_image` — remove one image from the post by position
- `reorder_images` — change the order of images in the post
- `clear_images` — remove all images (pool preserved)

## Images workflow
- Use `list_images` first to see what's already in the post and in the pool.
- To add an image:
    * from the pool → `use_candidate(pool_index)`
    * from a fresh search → `find_and_add_image(query)` then `use_candidate(...)`
    * from an external URL → `add_image_url(url)`
- To remove → `remove_image(position)`.
- To change order → `reorder_images([2, 0, 1])`.
- Never go over 4 images in one post — quality > quantity.
- If the admin wants coherent images (album), compare descriptions in the pool first before searching.

Respond in Russian. Be concise — the admin is in a chat, not reading an essay.
"""


def _get_post_lock(post_id: int) -> asyncio.Lock:
    """Get or create an asyncio lock for a specific post to serialize turns."""
    return _registry.get_post_lock(post_id)


@functools.lru_cache(maxsize=4)
def create_review_agent(model_name: str = "") -> Agent[ReviewAgentDeps, str]:
    """Create the PydanticAI review agent with all tools (cached per model)."""
    model_name = model_name or settings.channel.generation_model

    provider = OpenAIProvider(
        base_url=settings.openrouter.base_url,
        api_key=settings.openrouter.api_key,
    )
    model = OpenAIChatModel(model_name, provider=provider)

    from app.core.tool_trace import make_history_processor

    agent: Agent[ReviewAgentDeps, str] = Agent(
        model,
        deps_type=ReviewAgentDeps,
        output_type=str,
        retries=3,
        end_strategy="exhaustive",
        history_processors=[make_history_processor(_MAX_HISTORY)],
    )

    # Dynamic system prompt that injects the footer from deps
    @agent.system_prompt
    async def _system_prompt(ctx: RunContext[ReviewAgentDeps]) -> str:
        return _SYSTEM_PROMPT_TEMPLATE.replace(_FOOTER_PLACEHOLDER, ctx.deps.footer)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @agent.tool
    async def get_current_post(ctx: RunContext[ReviewAgentDeps]) -> str:
        """Get the current post text and images from DB."""
        from sqlalchemy import select

        from app.db.models import ChannelPost

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
            post = result.scalar_one_or_none()
            if post is None:
                return "Post not found in DB."
            parts = [post.post_text]
            if post.image_urls:
                parts.append(f"\n\nImages ({len(post.image_urls)}):")
                for i, url in enumerate(post.image_urls, 1):
                    parts.append(f"  {i}. {url}")
            elif post.image_url:
                parts.append(f"\n\nImage: {post.image_url}")
            else:
                parts.append("\n\nNo images attached.")
            return "\n".join(parts)

    @agent.tool
    async def web_search(ctx: RunContext[ReviewAgentDeps], query: str, count: int = 5) -> str:  # noqa: ARG001
        """Search the web for facts or context to enrich the post."""
        from app.channel.brave_search import brave_search_for_assistant

        api_key = settings.brave.api_key
        if not api_key:
            return "Web search is not configured (no Brave API key)."

        count = min(max(count, 1), 10)
        result = await brave_search_for_assistant(api_key, query, count=count)
        # Truncate to avoid blowing up context
        if len(result) > 2000:
            result = result[:2000] + "\n... (truncated)"
        return result

    @agent.tool
    async def update_post(ctx: RunContext[ReviewAgentDeps], new_text: str) -> str:
        """Replace the post text. Enforces footer and length limit. Updates the review message in Telegram."""
        from sqlalchemy import select

        from app.channel.generator import enforce_footer_and_length
        from app.channel.review.telegram_io import (
            _edit_review_message,
            build_review_keyboard,
            extract_source_btn_data,
        )
        from app.core.markdown import md_to_entities
        from app.db.models import ChannelPost

        # 1. Enforce footer and length
        new_text = enforce_footer_and_length(new_text, ctx.deps.footer)

        # 2. Update in DB
        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
            post = result.scalar_one_or_none()
            if not post:
                return "Post not found in DB."

            if post.status != PostStatus.DRAFT:
                return f"Cannot edit: post is already {post.status}."

            post.update_text(new_text)

            # 3. Update the review message in Telegram
            if post.review_message_id:
                source_btn_data = extract_source_btn_data(post)
                keyboard = build_review_keyboard(
                    ctx.deps.post_id,
                    source_items=source_btn_data,
                    channel_name=ctx.deps.channel_name,
                    channel_username=ctx.deps.channel_username,
                )
                try:
                    review_plain, review_entities = md_to_entities(new_text)
                    await _edit_review_message(
                        ctx.deps.bot,
                        ctx.deps.review_chat_id,
                        post.review_message_id,
                        review_plain,
                        review_entities,
                        keyboard,
                    )
                except Exception:
                    logger.exception("review_message_update_failed", post_id=ctx.deps.post_id)
                    review_msg_failed = True
                else:
                    review_msg_failed = False
            else:
                review_msg_failed = False

            await session.commit()

        char_count = len(new_text)
        logger.info("post_updated_by_agent", post_id=ctx.deps.post_id, chars=char_count)
        msg = f"Post updated ({char_count} chars)."
        if review_msg_failed:
            msg += " Warning: review message in chat could not be refreshed."
        return msg

    async def _refresh_review_message(ctx: RunContext[ReviewAgentDeps], post: Any) -> str | None:
        """Delegate to the telegram_io rebuild helper.

        The ``post`` argument is unused — the helper re-fetches from DB to avoid
        stale state. Kept for API compatibility with earlier callers.
        """
        del post
        from sqlalchemy import select as _select

        from app.channel.review.service import extract_source_btn_data
        from app.channel.review.telegram_io import _rebuild_review_message, build_review_keyboard
        from app.db.models import ChannelPost

        try:
            async with ctx.deps.session_maker() as session:
                r = await session.execute(_select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
                fresh_post = r.scalar_one_or_none()

            if fresh_post is None:
                return "Warning: post not found during refresh."

            keyboard = build_review_keyboard(
                ctx.deps.post_id,
                source_items=extract_source_btn_data(fresh_post),
                channel_name=ctx.deps.channel_name,
                channel_username=ctx.deps.channel_username,
            )
            await _rebuild_review_message(
                ctx.deps.bot,
                ctx.deps.review_chat_id,
                ctx.deps.post_id,
                ctx.deps.session_maker,
                keyboard,
            )

            # Register the new pult in the reply chain (post.review_message_id was
            # updated inside _rebuild_review_message).
            async with ctx.deps.session_maker() as session:
                r = await session.execute(_select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
                refreshed = r.scalar_one_or_none()
            if refreshed and refreshed.review_message_id:
                register_message(refreshed.review_message_id, ctx.deps.post_id)
                await persist_message_to_db(ctx.deps.session_maker, ctx.deps.post_id, refreshed.review_message_id)

            return None
        except Exception:
            logger.exception("review_message_refresh_failed", post_id=ctx.deps.post_id)
            return "Warning: review message could not be refreshed."

    # ------------------------------------------------------------------
    # Image tools (granular, backed by app.channel.review.image_tools)
    # ------------------------------------------------------------------

    def _image_deps(ctx: RunContext[ReviewAgentDeps]) -> Any:
        from app.channel.review.image_tools import ImageToolsDeps

        return ImageToolsDeps(
            session_maker=ctx.deps.session_maker,
            post_id=ctx.deps.post_id,
            channel_id=ctx.deps.channel_id,
            api_key=settings.openrouter.api_key,
            vision_model=settings.channel.vision_model,
            brave_api_key=settings.brave.api_key,
        )

    @agent.tool
    async def list_images(ctx: RunContext[ReviewAgentDeps]) -> str:
        """List current images + candidate pool."""
        from app.channel.review.image_tools import list_images_op

        return await list_images_op(_image_deps(ctx))

    @agent.tool
    async def use_candidate(ctx: RunContext[ReviewAgentDeps], pool_index: int, position: int | None = None) -> str:
        """Promote a pool candidate into the post. Refreshes the review message."""
        from app.channel.review.image_tools import use_candidate_op

        out = await use_candidate_op(_image_deps(ctx), pool_index=pool_index, position=position)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def add_image_url(ctx: RunContext[ReviewAgentDeps], url: str, position: int | None = None) -> str:
        """Add an external image URL to the post (validated)."""
        from app.channel.review.image_tools import add_image_url_op

        out = await add_image_url_op(_image_deps(ctx), url=url, position=position)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def find_and_add_image(ctx: RunContext[ReviewAgentDeps], query: str) -> str:
        """Search Brave for images matching ``query`` and add the best to the pool (not auto-selected)."""
        from app.channel.review.image_tools import find_and_add_image_op

        return await find_and_add_image_op(_image_deps(ctx), query=query)

    @agent.tool
    async def remove_image(ctx: RunContext[ReviewAgentDeps], position: int) -> str:
        """Remove the image at ``position`` from the post. Candidate stays in pool."""
        from app.channel.review.image_tools import remove_image_op

        out = await remove_image_op(_image_deps(ctx), position=position)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def reorder_images(ctx: RunContext[ReviewAgentDeps], order: list[int]) -> str:
        """Reorder selected images by current-position indices."""
        from app.channel.review.image_tools import reorder_images_op

        out = await reorder_images_op(_image_deps(ctx), order=order)
        await _refresh_after_change(ctx)
        return out

    @agent.tool
    async def clear_images(ctx: RunContext[ReviewAgentDeps]) -> str:
        """Remove all images from the post (pool kept for later re-use)."""
        from app.channel.review.image_tools import clear_images_op

        out = await clear_images_op(_image_deps(ctx))
        await _refresh_after_change(ctx)
        return out

    async def _refresh_after_change(ctx: RunContext[ReviewAgentDeps]) -> None:
        """Re-fetch the post and rebuild the review message."""
        await _refresh_review_message(ctx, None)

    return agent


# ---------------------------------------------------------------------------
# Entry point — one conversation turn
# ---------------------------------------------------------------------------


async def review_agent_turn(
    post_id: int,
    user_message: str,
    deps: ReviewAgentDeps,
    model: str = "",
) -> str:
    """Run one turn of the review agent conversation.

    Maintains per-post conversation history for multi-turn editing.
    Uses per-post locks to serialize concurrent turns for the same post.
    Returns the agent's text response.
    """
    lock = _get_post_lock(post_id)
    async with lock:
        return await _review_agent_turn_inner(post_id, user_message, deps, model)


async def _review_agent_turn_inner(
    post_id: int,
    user_message: str,
    deps: ReviewAgentDeps,
    model: str,
) -> str:
    from app.core.tool_trace import format_response_with_trace

    _registry.evict_stale()

    history = _registry.get_history(post_id)
    agent = create_review_agent(model)

    try:
        result = await asyncio.wait_for(
            agent.run(
                user_message,
                deps=deps,
                message_history=history,
            ),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("review_agent_timeout", post_id=post_id, timeout=_AGENT_TIMEOUT_SECONDS)
        return "Превышено время ожидания агента. Попробуй ещё раз или упрости запрос."
    except Exception:
        logger.exception("review_agent_error", post_id=post_id)
        return "Ошибка агента. Попробуй ещё раз."

    # Collect per-turn messages for the trace.  new_messages() is robust to
    # history trimming inside history_processors (slicing by pre-run length
    # can yield an empty range once the cap is hit).
    turn_msgs: list[ModelMessage] = list(result.new_messages())

    # Check if model skipped update_post on what looks like an edit request
    if _looks_like_edit_request(user_message) and not _has_tool_call(result, "update_post"):
        logger.warning("review_agent_skipped_update_post", post_id=post_id)
        # Retry once with explicit nudge
        try:
            retry_history = list(result.all_messages())
            result = await asyncio.wait_for(
                agent.run(
                    "Ты не вызвал update_post. Пожалуйста, вызови get_current_post, "
                    "внеси изменения и обязательно вызови update_post с полным текстом.",
                    deps=deps,
                    message_history=retry_history,
                ),
                timeout=_AGENT_TIMEOUT_SECONDS,
            )
            turn_msgs.extend(result.new_messages())
        except Exception:
            logger.exception("review_agent_retry_error", post_id=post_id)

    # Track usage/cost
    from app.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage

    model_name = model or settings.channel.generation_model
    usage = extract_usage_from_pydanticai_result(result, model_name, "review_agent")
    if usage:
        await log_usage(usage)

    # Save conversation for continuity (trimming handled by history_processors)
    _registry.set_history(post_id, list(result.all_messages()))

    logger.info(
        "review_agent_turn_done",
        post_id=post_id,
        history_len=_registry.history_length(post_id),
    )

    return format_response_with_trace(turn_msgs, result.output)


def _has_tool_call(result: Any, tool_name: str) -> bool:
    """Check if a specific tool was called in the agent's response messages."""
    for msg in result.all_messages():
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                    return True
    return False


# Keywords that indicate the admin wants to edit the post
_EDIT_KEYWORDS = (
    "измени",
    "поменяй",
    "исправ",
    "сократи",
    "удлини",
    "перепиши",
    "переделай",
    "убери",
    "добавь",
    "замени",
    "сделай",
    "переведи",
    "отредактируй",
    "подправ",
    "форматиро",
    "короче",
    "длиннее",
    "обнови",
    "перефразируй",
    "упрости",
)


def _looks_like_edit_request(text: str) -> bool:
    """Heuristic: does the user message look like a post edit request?"""
    lower = text.lower()
    return any(kw in lower for kw in _EDIT_KEYWORDS)
