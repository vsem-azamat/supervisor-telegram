"""Review service — business logic for post state transitions and data extraction.

Two Telegram/Telethon concerns leak into this module: (1) cancelling scheduled
messages when a scheduled post is rejected, (2) cancelling scheduled messages
when a scheduled post is deleted. Both are needed to keep the "reject" and
"delete" flows atomic — if we moved those Telegram calls to presentation, we'd
split a single logical transition across two layers. Accepted trade-off.

Telegram-specific rendering (keyboards, send/edit, button layouts) still lives
in telegram_io.py.
"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from app.channel.embeddings import EMBEDDING_MODEL
from app.channel.exceptions import EmbeddingError
from app.channel.generator import DEFAULT_FOOTER, enforce_footer_and_length
from app.channel.llm_client import openrouter_chat_completion
from app.core.enums import PostStatus
from app.core.logging import get_logger
from app.db.models import ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.channel.generator import GeneratedPost
    from app.channel.sources import ContentItem

logger = get_logger("channel.review_service")

# ── Callback data prefixes (shared contract between keyboards and handlers) ──

CB_APPROVE = "chpost:approve:"
CB_REJECT = "chpost:reject:"
CB_REGEN = "chpost:regen:"
CB_SHORTER = "chpost:shorter:"
CB_LONGER = "chpost:longer:"
CB_DELETE = "chpost:delete:"
CB_SCHEDULE = "chpost:sched:"
CB_SCHEDULE_PICK = "chpost:sp:"
CB_PUBLISH_NOW = "chpost:pubnow:"
CB_TRANSLATE = "chpost:translate:"
CB_BACK = "chpost:back:"

# ── Identity / storage constants (stable contracts; do not tune casually) ──

# Length of the sha256 prefix used as a fallback external_id. Historical rows
# were stored at this width; changing it breaks dedup lookups against old posts.
EXT_ID_HASH_LENGTH = 16

# Number of characters from the post text hashed into a fallback external_id,
# and also used as fallback embedding input when there are no source_items.
EXT_ID_HASH_INPUT_CHARS = 200

# Max characters of the source title stored on ChannelPost.title (display only).
REVIEW_TITLE_MAX_CHARS = 200

# Review-keyboard source buttons (max count and per-button title width).
REVIEW_SOURCE_BUTTON_COUNT = 2
REVIEW_SOURCE_TITLE_CHARS = 25

# Max source items persisted on ChannelPost.source_items.
REVIEW_SOURCE_ITEMS_STORED = 5

# ── Pure data helpers ──


def extract_source_btn_data(post: ChannelPost) -> list[dict[str, str]]:
    """Extract source title+url pairs from a post for keyboard buttons."""
    if not post.source_items:
        return []
    items: list[dict[str, str]] = []
    for src in post.source_items[:REVIEW_SOURCE_BUTTON_COUNT]:
        url = src.get("url") or src.get("source_url")
        title = src.get("title", "")
        if url and url.startswith(("http://", "https://")):
            items.append({"title": title[:REVIEW_SOURCE_TITLE_CHARS], "url": url})
    return items


def extract_source_urls(post: ChannelPost) -> list[str]:
    """Extract unique source URLs from a post's source_items."""
    if not post.source_items:
        return []
    urls: list[str] = []
    for item in post.source_items:
        source_url = item.get("source_url")
        if source_url and source_url not in urls:
            urls.append(source_url)
    return urls


# ── DB / business-logic operations ──


async def create_review_post(
    channel_id: int,
    post: GeneratedPost,
    source_items: list[ContentItem],
    review_chat_id: int | str,
    session: AsyncSession,
    *,
    api_key: str = "",
    embedding_model: str = "",
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> ChannelPost | None:
    """Create a ChannelPost record and attach its embedding in the same session.

    Returns the ORM object (flushed, not committed), or None if a post with
    the same (channel_id, external_id) already exists.

    Raises EmbeddingError if ``api_key`` is provided but the embedding API
    fails — the caller must abort rather than skip dedup silently. Embeddings
    are computed here (not after commit) so they share the outer transaction
    and are visible to subsequent dedup queries as soon as the caller commits.
    """
    # session_maker kept for API compatibility with older callers; embeddings
    # no longer require a separate session.
    del session_maker
    if source_items:
        ext_id = source_items[0].external_id
    else:
        ext_id = sha256(post.text[:EXT_ID_HASH_INPUT_CHARS].encode()).hexdigest()[:EXT_ID_HASH_LENGTH]

    source_data = [
        {"title": s.title, "url": s.url, "source_url": s.source_url, "external_id": s.external_id}
        for s in source_items[:REVIEW_SOURCE_ITEMS_STORED]
    ]

    db_post = ChannelPost(
        channel_id=channel_id,
        external_id=ext_id,
        title=source_items[0].title[:REVIEW_TITLE_MAX_CHARS] if source_items else "Generated post",
        post_text=post.text,
        image_url=post.image_url,
        image_urls=post.image_urls or None,
        source_items=source_data,
        review_chat_id=int(review_chat_id) if review_chat_id else 0,
    )
    session.add(db_post)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.warning("duplicate_post_skipped", channel_id=channel_id, external_id=ext_id)
        return None

    if api_key:
        from app.channel.semantic_dedup import build_embedding_text, compute_embedding

        if source_items:
            embed_text = build_embedding_text(source_items[0].title, source_items[0].body)
        else:
            embed_text = post.text[:EXT_ID_HASH_INPUT_CHARS]
        model = embedding_model or EMBEDDING_MODEL
        try:
            vector = await compute_embedding(embed_text, api_key=api_key, model=model)
        except EmbeddingError:
            # Roll back so the post is not persisted without dedup coverage.
            await session.rollback()
            logger.warning("review_post_aborted_embedding_unavailable", channel_id=channel_id, external_id=ext_id)
            raise
        db_post.embedding = vector
        db_post.embedding_model = model
        logger.info("embedding_attached", post_id=db_post.id, channel_id=channel_id, model=model)

    return db_post


async def approve_post(
    post_id: int,
    channel_id: int | str,
    publish_fn: Any,
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[str, int | None]:
    """Approve and publish a post. Returns (status_message, published_msg_id | None).

    ``publish_fn`` is an async callable ``(channel_id, GeneratedPost) -> int | None``
    that actually sends the message to the channel (injected by the presentation layer).
    """
    from sqlalchemy import select

    from app.channel.source_manager import update_source_relevance

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found.", None
        if post.status == PostStatus.APPROVED:
            return "Already published.", None
        if post.status == PostStatus.SCHEDULED:
            return "Post is scheduled. Use 'Publish now' to send immediately.", None

        source_urls = extract_source_urls(post)

        try:
            # Atomically reserve a daily slot BEFORE publishing
            from app.channel.channel_repo import try_reserve_daily_slot

            slot_reserved = await try_reserve_daily_slot(session_maker, post.channel_id)
            if not slot_reserved:
                logger.warning("daily_limit_reached_at_approve", post_id=post_id, channel_id=post.channel_id)
                return "Daily post limit reached. Try again tomorrow.", None

            from app.channel.generator import GeneratedPost

            # Publish only the single image shown during review (not the full image_urls array).
            # The review message displays only image_url; publishing image_urls would
            # send photos the reviewer never saw.
            reviewed_image = post.image_url
            gen_post = GeneratedPost(
                text=post.post_text,
                image_url=reviewed_image,
                image_urls=[reviewed_image] if reviewed_image else [],
            )
            msg_id = await publish_fn(channel_id, gen_post)
            if not msg_id:
                return "Failed to publish.", None
            post.approve(msg_id)
            await session.commit()
            logger.info("post_approved", post_id=post_id, msg_id=msg_id)

            if source_urls:
                await update_source_relevance(session_maker, source_urls, approved=True)

            return f"Published! (msg #{msg_id})", msg_id
        except Exception:
            logger.exception("approve_publish_error", post_id=post_id)
            return "Failed to publish.", None


async def reject_post(
    post_id: int,
    session_maker: async_sessionmaker[AsyncSession],
    reason: str | None = None,
) -> str:
    """Reject a post. Returns status message."""
    from sqlalchemy import select

    from app.channel.source_manager import update_source_relevance

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status == PostStatus.REJECTED:
            return "Already rejected."
        if post.status == PostStatus.APPROVED:
            return "Already published — cannot reject."

        was_scheduled = post.status == PostStatus.SCHEDULED
        scheduled_tg_id = post.scheduled_telegram_id if was_scheduled else None

        source_urls = extract_source_urls(post)
        post.reject(reason)
        await session.commit()
        logger.info("post_rejected", post_id=post_id)

        # Delete Telegram scheduled message if it was scheduled
        if was_scheduled and scheduled_tg_id:
            try:
                from app.core.container import container
                from app.db.models import Channel

                tc = container.get_telethon_client()
                if tc:
                    ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
                    ch = ch_result.scalar_one_or_none()
                    if ch:
                        from app.channel.schedule_manager import _resolve_chat_id

                        chat_id = _resolve_chat_id(ch)
                        await tc.delete_scheduled_messages(chat_id, [scheduled_tg_id])
            except Exception:
                logger.warning("cancel_scheduled_on_reject_failed", post_id=post_id, exc_info=True)

        if source_urls:
            await update_source_relevance(session_maker, source_urls, approved=False)

        return "Post rejected."


async def delete_post(
    post_id: int,
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[str, ChannelPost | None]:
    """Soft-delete a post (set status=SKIPPED). Keeps it in DB for dedup.

    The caller is responsible for removing the Telegram review message.
    """
    from sqlalchemy import select

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found.", None
        if post.status == PostStatus.APPROVED:
            return "Already published — cannot delete.", None
        if post.status == PostStatus.SKIPPED:
            return "Already skipped.", None

        post.skip()
        await session.commit()
        logger.info("post_skipped", post_id=post_id)

        return "Post skipped.", post


async def edit_post_text(
    post_id: int,
    instruction: str,
    api_key: str,
    model: str,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    http_timeout: int = 30,
    temperature: float = 0.3,
    footer: str = "",
) -> tuple[str, ChannelPost | None]:
    """Edit a post via LLM based on instruction. Returns (status_message, updated_post_or_None).

    Does NOT touch Telegram messages — the caller handles review message updates.
    """
    from sqlalchemy import select

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found.", None
        if post.status == PostStatus.APPROVED:
            return "Already published — cannot edit.", None
        if post.status == PostStatus.REJECTED:
            return "Post was rejected — cannot edit.", None
        if post.status == PostStatus.SKIPPED:
            return "Post was skipped — cannot edit.", None

        effective_footer = footer.strip() or DEFAULT_FOOTER

        try:
            new_text = await openrouter_chat_completion(
                api_key=api_key,
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a post editor for the Konnekt Telegram channel "
                            "(CIS students in Czech Republic). "
                            "Edit the post according to the instruction. "
                            "Return ONLY the edited post text in Markdown format. "
                            "No explanations.\n\n"
                            "RULES YOU MUST FOLLOW:\n"
                            "- LENGTH: 300-500 chars for news, up to 700 for analysis. "
                            "Hard limit 900 chars.\n"
                            "- TONE: Friendly, slightly witty — like a smart friend sharing news. "
                            "Not too formal, not too casual.\n"
                            "  BAD: 'Уважаемые студенты! Администрация сообщает...'\n"
                            "  BAD: 'ааа братцы дедлайн продлили!!!'\n"
                            "  GOOD: 'Если вы ещё не подали заявку — есть хорошая новость.'\n"
                            "- Always leave blank lines between headline, paragraphs, and footer.\n"
                            "- Max 1 emoji (at headline start), max 1 exclamation mark per post.\n"
                            "- Use standard Markdown: **bold**, *italic*, [link](url). "
                            "No HTML tags, no hashtags.\n"
                            f"- ALWAYS end with the channel footer:\n  {effective_footer}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Current post:\n{post.post_text}\n\nInstruction: {instruction}",
                    },
                ],
                operation="edit",
                temperature=temperature,
                timeout=http_timeout,
            )
            if not new_text:
                return "Edit failed.", None

            if not isinstance(new_text, str):
                new_text = str(new_text)
            new_text = enforce_footer_and_length(new_text, effective_footer)
            post.update_text(new_text)

            # If post is scheduled, update the Telegram scheduled message too
            if post.status == PostStatus.SCHEDULED and post.scheduled_telegram_id:
                try:
                    from sqlalchemy import select as sa_select

                    from app.channel.schedule_manager import update_scheduled_text
                    from app.core.container import container
                    from app.db.models import Channel

                    tc = container.get_telethon_client()
                    if tc:
                        ch_result = await session.execute(
                            sa_select(Channel).where(Channel.telegram_id == post.channel_id)
                        )
                        ch = ch_result.scalar_one_or_none()
                        if ch:
                            await update_scheduled_text(tc, ch, post)
                except Exception:
                    logger.warning("scheduled_message_update_failed", post_id=post_id, exc_info=True)

            await session.commit()
            logger.info("post_edited", post_id=post_id, instruction=instruction[:60])
            return "Post updated.", post

        except Exception:
            logger.exception("edit_error", post_id=post_id)
            return "Edit failed.", None


async def regen_post_text(
    post_id: int,
    api_key: str,
    model: str,
    language: str,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    footer: str = "",
) -> tuple[str, ChannelPost | None]:
    """Regenerate a post from its original sources. Returns (status_message, updated_post_or_None).

    Does NOT touch Telegram messages — the caller handles review message updates.
    """
    from sqlalchemy import select

    from app.channel.generator import generate_post
    from app.channel.sources import ContentItem

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found.", None
        if post.status == PostStatus.APPROVED:
            return "Already published — cannot regenerate.", None
        if post.status == PostStatus.REJECTED:
            return "Post was rejected — cannot regenerate.", None
        if post.status == PostStatus.SKIPPED:
            return "Post was skipped — cannot regenerate.", None

        items = []
        if post.source_items:
            for src in post.source_items:
                items.append(
                    ContentItem(
                        source_url=src.get("source_url", ""),
                        external_id="regen",
                        title=src.get("title", ""),
                        body=src.get("summary", src.get("title", "")),
                        url=src.get("url"),
                    )
                )

        if not items:
            return "No source data to regenerate from.", None

        new_post = await generate_post(items, api_key=api_key, model=model, language=language, footer=footer)
        if not new_post:
            return "Regeneration failed.", None

        post.update_text(new_post.text)
        await session.commit()
        logger.info("post_regenerated", post_id=post_id)
        return "Post regenerated.", post
