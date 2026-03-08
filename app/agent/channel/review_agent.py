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
from app.core.logging import get_logger
from app.domain.value_objects import PostStatus

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
    channel_id: str
    channel_name: str
    channel_username: str | None
    footer: str
    review_chat_id: int | str


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------

_review_conversations: dict[int, list[ModelMessage]] = {}  # post_id -> message history
_review_last_access: dict[int, float] = {}
_MAX_REVIEW_CONVERSATIONS = 200
_REVIEW_CONVERSATION_TTL = 14400  # 4 hours
_MAX_HISTORY = 40
_AGENT_TIMEOUT_SECONDS = 60


def _evict_review_conversations() -> None:
    """Evict conversations idle for >TTL, then enforce max cap (LRU)."""
    now = time.monotonic()

    # 1. Evict idle conversations
    expired = [pid for pid, ts in _review_last_access.items() if now - ts > _REVIEW_CONVERSATION_TTL]
    for pid in expired:
        _review_conversations.pop(pid, None)
        _review_last_access.pop(pid, None)

    # 2. Enforce max cap — evict least recently used
    if len(_review_conversations) > _MAX_REVIEW_CONVERSATIONS:
        sorted_by_access = sorted(_review_last_access.items(), key=lambda x: x[1])
        to_remove = len(_review_conversations) - _MAX_REVIEW_CONVERSATIONS
        for pid, _ in sorted_by_access[:to_remove]:
            _review_conversations.pop(pid, None)
            _review_last_access.pop(pid, None)


def clear_review_conversation(post_id: int) -> None:
    """Clear conversation for a post (call on approve/reject)."""
    _review_conversations.pop(post_id, None)
    _review_last_access.pop(post_id, None)
    logger.debug("review_conversation_cleared", post_id=post_id)


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
  GOOD: 'Если вы ещё не подали заявку — есть хорошая новость.'
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
6. If the admin asks about images, use `find_new_images` and then `replace_images`.

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
- `update_post` — save the edited text (MUST call to apply any changes)
- `find_new_images` — search for images by keywords
- `replace_images` — replace the post's images with new URLs

Respond in Russian. Be concise — the admin is in a chat, not reading an essay.
"""


_post_locks: dict[int, asyncio.Lock] = {}


def _get_post_lock(post_id: int) -> asyncio.Lock:
    """Get or create an asyncio lock for a specific post to serialize turns."""
    if post_id not in _post_locks:
        _post_locks[post_id] = asyncio.Lock()
    return _post_locks[post_id]


@functools.lru_cache(maxsize=4)
def create_review_agent(model_name: str = "") -> Agent[ReviewAgentDeps, str]:
    """Create the PydanticAI review agent with all tools (cached per model)."""
    model_name = model_name or settings.channel.generation_model

    provider = OpenAIProvider(
        base_url=settings.agent.openrouter_base_url,
        api_key=settings.agent.openrouter_api_key,
    )
    model = OpenAIChatModel(model_name, provider=provider)

    agent: Agent[ReviewAgentDeps, str] = Agent(
        model,
        deps_type=ReviewAgentDeps,
        output_type=str,
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
        """Get the current post text from DB."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelPost

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost.post_text).where(ChannelPost.id == ctx.deps.post_id))
            row = result.scalar_one_or_none()
            if row is None:
                return "Post not found in DB."
            return str(row)

    @agent.tool
    async def web_search(ctx: RunContext[ReviewAgentDeps], query: str, count: int = 5) -> str:  # noqa: ARG001
        """Search the web for facts or context to enrich the post."""
        from app.agent.channel.brave_search import brave_search_for_assistant

        api_key = settings.agent.brave_api_key
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

        from app.agent.channel.generator import enforce_footer_and_length
        from app.agent.channel.review import (
            _build_review_keyboard,
            _edit_review_message,
            _extract_source_btn_data,
        )
        from app.core.markdown import md_to_entities
        from app.infrastructure.db.models import ChannelPost

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
                source_btn_data = _extract_source_btn_data(post)
                keyboard = _build_review_keyboard(
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

    @agent.tool
    async def find_new_images(ctx: RunContext[ReviewAgentDeps], query: str) -> str:
        """Search for new images by keywords. Returns found image URLs."""
        from app.agent.channel.images import find_images_for_post

        _ = ctx  # deps not needed for image search itself
        images = await find_images_for_post(keywords=query, source_urls=[])
        if not images:
            return "No images found for the given query."
        lines = [f"Found {len(images)} image(s):"]
        for i, url in enumerate(images, 1):
            lines.append(f"{i}. {url}")
        return "\n".join(lines)

    @agent.tool
    async def replace_images(ctx: RunContext[ReviewAgentDeps], image_urls: list[str]) -> str:
        """Replace the post's images with new ones. Max 3 images."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelPost

        image_urls = image_urls[:3]

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == ctx.deps.post_id))
            post = result.scalar_one_or_none()
            if not post:
                return "Post not found in DB."

            if post.status != PostStatus.DRAFT:
                return f"Cannot edit: post is already {post.status}."

            post.image_url = image_urls[0] if image_urls else None
            post.image_urls = image_urls if image_urls else None
            await session.commit()

        logger.info("images_replaced_by_agent", post_id=ctx.deps.post_id, count=len(image_urls))
        return f"Images replaced: {len(image_urls)} image(s) set."

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
    _evict_review_conversations()

    history = _review_conversations.get(post_id)
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
        except Exception:
            logger.exception("review_agent_retry_error", post_id=post_id)

    # Track usage/cost
    from app.agent.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage

    model_name = model or settings.channel.generation_model
    usage = extract_usage_from_pydanticai_result(result, model_name, "review_agent")
    if usage:
        await log_usage(usage)

    # Save conversation for continuity
    all_msgs = list(result.all_messages())
    _review_conversations[post_id] = all_msgs
    _review_last_access[post_id] = time.monotonic()

    # Trim long history — keep last N messages
    if len(all_msgs) > _MAX_HISTORY:
        _review_conversations[post_id] = all_msgs[-_MAX_HISTORY:]

    logger.info(
        "review_agent_turn_done",
        post_id=post_id,
        history_len=len(_review_conversations[post_id]),
    )
    return result.output


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
