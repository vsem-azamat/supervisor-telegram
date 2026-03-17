"""Review service — pure business logic for post state transitions and data extraction.

This module contains NO Telegram/aiogram dependencies.
All Telegram-specific rendering lives in presentation.py (presentation layer).
"""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from app.agent.channel.embeddings import EMBEDDING_MODEL
from app.agent.channel.generator import DEFAULT_FOOTER, enforce_footer_and_length
from app.agent.channel.llm_client import openrouter_chat_completion
from app.core.enums import PostStatus
from app.core.logging import get_logger
from app.infrastructure.db.models import ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.generator import GeneratedPost
    from app.agent.channel.sources import ContentItem

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

# ── Pure data helpers ──


def extract_source_btn_data(post: ChannelPost) -> list[dict[str, str]]:
    """Extract source title+url pairs from a post for keyboard buttons."""
    if not post.source_items:
        return []
    items: list[dict[str, str]] = []
    for src in post.source_items[:2]:
        url = src.get("url") or src.get("source_url")
        title = src.get("title", "")
        if url and url.startswith(("http://", "https://")):
            items.append({"title": title[:25], "url": url})
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
    channel_id: str,
    post: GeneratedPost,
    source_items: list[ContentItem],
    review_chat_id: int | str,
    session: AsyncSession,
    *,
    api_key: str = "",
    embedding_model: str = "",
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> ChannelPost | None:
    """Create a ChannelPost record in DB, store embedding.

    Returns the ORM object (flushed, not committed), or None if a post with
    the same (channel_id, external_id) already exists.
    """
    ext_id = source_items[0].external_id if source_items else sha256(post.text[:200].encode()).hexdigest()[:16]

    source_data = [
        {"title": s.title, "url": s.url, "source_url": s.source_url, "external_id": s.external_id}
        for s in source_items[:5]
    ]

    db_post = ChannelPost(
        channel_id=channel_id,
        external_id=ext_id,
        title=source_items[0].title[:200] if source_items else "Generated post",
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

    # Store embedding (non-blocking, best-effort)
    if api_key and session_maker:
        try:
            from app.agent.channel.semantic_dedup import store_post_embedding

            embed_text = f"{source_items[0].title} {source_items[0].body[:100]}" if source_items else post.text[:200]
            await store_post_embedding(
                post_id=db_post.id,
                text_for_embedding=embed_text,
                api_key=api_key,
                session_maker=session_maker,
                model=embedding_model or EMBEDDING_MODEL,
            )
        except Exception:
            logger.warning("embedding_store_failed", post_id=db_post.id, exc_info=True)

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

    from app.agent.channel.source_manager import update_source_relevance

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
            from app.agent.channel.channel_repo import try_reserve_daily_slot

            slot_reserved = await try_reserve_daily_slot(session_maker, post.channel_id)
            if not slot_reserved:
                logger.warning("daily_limit_reached_at_approve", post_id=post_id, channel_id=post.channel_id)
                return "Daily post limit reached. Try again tomorrow.", None

            from app.agent.channel.generator import GeneratedPost

            gen_post = GeneratedPost(
                text=post.post_text,
                image_url=getattr(post, "image_url", None),
                image_urls=getattr(post, "image_urls", None) or [],
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

    from app.agent.channel.source_manager import update_source_relevance

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
                from app.infrastructure.db.models import Channel

                tc = container.get_telethon_client()
                if tc:
                    ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
                    ch = ch_result.scalar_one_or_none()
                    if ch:
                        from app.agent.channel.schedule_manager import _resolve_chat_id

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
    """Delete a post from DB. Returns (status_message, deleted_post_or_None).

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

        review_msg_id = post.review_message_id
        # Create a minimal copy of info needed before deletion
        deleted_info = type("DeletedPostInfo", (), {"review_message_id": review_msg_id})()  # noqa: E501

        await session.delete(post)
        await session.commit()
        logger.info("post_deleted", post_id=post_id)

        return "Post deleted.", deleted_info


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

            new_text = enforce_footer_and_length(new_text, effective_footer)
            post.update_text(new_text)

            # If post is scheduled, update the Telegram scheduled message too
            if post.status == PostStatus.SCHEDULED and post.scheduled_telegram_id:
                try:
                    from sqlalchemy import select as sa_select

                    from app.agent.channel.schedule_manager import update_scheduled_text
                    from app.core.container import container
                    from app.infrastructure.db.models import Channel

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

    from app.agent.channel.generator import generate_post
    from app.agent.channel.sources import ContentItem

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id).with_for_update())
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found.", None
        if post.status == PostStatus.APPROVED:
            return "Already published — cannot regenerate.", None
        if post.status == PostStatus.REJECTED:
            return "Post was rejected — cannot regenerate.", None

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
