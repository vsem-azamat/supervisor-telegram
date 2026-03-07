"""Review flow — sends drafts to review channel with inline buttons, handles callbacks."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, URLInputFile

from app.agent.channel.generator import KONNEKT_FOOTER
from app.agent.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger
from app.core.markdown import md_to_entities
from app.infrastructure.db.models import ChannelPost

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.generator import GeneratedPost
    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.review")

# Callback data prefixes
CB_APPROVE = "chpost:approve:"
CB_REJECT = "chpost:reject:"
CB_REGEN = "chpost:regen:"
CB_SHORTER = "chpost:shorter:"
CB_LONGER = "chpost:longer:"
CB_TRANSLATE = "chpost:translate:"


def _build_review_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Build inline keyboard for post review."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"{CB_APPROVE}{post_id}"),
                InlineKeyboardButton(text="Reject", callback_data=f"{CB_REJECT}{post_id}"),
                InlineKeyboardButton(text="Regen", callback_data=f"{CB_REGEN}{post_id}"),
            ],
            [
                InlineKeyboardButton(text="Shorter", callback_data=f"{CB_SHORTER}{post_id}"),
                InlineKeyboardButton(text="Longer", callback_data=f"{CB_LONGER}{post_id}"),
                InlineKeyboardButton(text="Translate", callback_data=f"{CB_TRANSLATE}{post_id}"),
            ],
        ]
    )


def _format_review_message(post_text: str, sources: list[ContentItem] | None = None) -> str:
    """Format the review message with metadata."""
    parts = [post_text, "\n\n---"]

    if sources:
        source_lines = []
        for s in sources[:3]:
            source_lines.append(f"  {s.title[:50]}")
        parts.append("*Sources:*\n" + "\n".join(source_lines))

    parts.append("*Reply to this message to edit via conversation.*")
    return "\n".join(parts)


async def _send_review_message(
    bot: Bot,
    chat_id: int | str,
    text: str,
    keyboard: InlineKeyboardMarkup,
    image_url: str | None = None,
) -> Message:
    """Send review message — photo with caption if image available, else text."""
    plain, entities = md_to_entities(text)

    if image_url and len(plain) <= 1024:
        try:
            photo = URLInputFile(image_url)
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=plain,
                caption_entities=entities,
                reply_markup=keyboard,
            )
        except Exception:
            logger.warning("review_photo_failed_fallback_to_text")

    return await bot.send_message(
        chat_id=chat_id,
        text=plain,
        entities=entities,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def send_for_review(
    bot: Bot,
    review_chat_id: int | str,
    channel_id: str,
    post: GeneratedPost,
    source_items: list[ContentItem],
    session_maker: async_sessionmaker[AsyncSession],
) -> int | None:
    """Send a generated post to the review channel with inline buttons.

    Creates a ChannelPost record in DB and returns its ID.
    """
    # Use the source item's external_id for dedup (matches the fetch-time dedup query)
    ext_id = source_items[0].external_id if source_items else sha256(post.text[:200].encode()).hexdigest()[:16]

    # Save to DB first
    source_data = [
        {"title": s.title, "url": s.url, "source_url": s.source_url, "external_id": s.external_id}
        for s in source_items[:5]
    ]

    async with session_maker() as session:
        db_post = ChannelPost(
            channel_id=channel_id,
            external_id=ext_id,
            title=source_items[0].title[:200] if source_items else "Generated post",
            post_text=post.text,
            image_url=post.image_url,
            image_urls=post.image_urls or None,
            source_items=source_data,
            review_chat_id=int(review_chat_id)
            if isinstance(review_chat_id, str) and review_chat_id.lstrip("-").isdigit()
            else 0,
        )
        session.add(db_post)
        await session.flush()
        post_id = db_post.id

        # Send to review channel (photo + caption or text)
        review_text = _format_review_message(post.text, source_items)
        keyboard = _build_review_keyboard(post_id)

        try:
            msg = await _send_review_message(bot, review_chat_id, review_text, keyboard, post.image_url)
            db_post.review_message_id = msg.message_id
            await session.commit()
            logger.info("review_sent", post_id=post_id, review_msg=msg.message_id)
            return post_id
        except Exception:
            logger.exception("review_send_error", review_chat_id=review_chat_id)
            await session.rollback()
            return None


async def _extract_source_urls(post: ChannelPost) -> list[str]:
    """Extract unique source URLs from a post's source_items."""
    if not post.source_items:
        return []
    urls: list[str] = []
    for item in post.source_items:
        source_url = item.get("source_url")
        if source_url and source_url not in urls:
            urls.append(source_url)
    return urls


async def handle_approve(
    bot: Bot,
    post_id: int,
    channel_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Approve and publish a post. Returns status message."""
    from sqlalchemy import select

    from app.agent.channel.source_manager import update_source_relevance

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status == "approved":
            return "Already published."

        source_urls = await _extract_source_urls(post)

        try:
            from app.agent.channel.generator import GeneratedPost
            from app.agent.channel.publisher import publish_post as _publish

            gen_post = GeneratedPost(
                text=post.post_text,
                image_url=getattr(post, "image_url", None),
                image_urls=getattr(post, "image_urls", None) or [],
            )
            msg_id = await _publish(bot, channel_id, gen_post)
            if not msg_id:
                return "Failed to publish."
            post.approve(msg_id)
            await session.commit()
            logger.info("post_approved", post_id=post_id, msg_id=msg_id)

            # Boost relevance of contributing sources
            if source_urls:
                await update_source_relevance(session_maker, source_urls, approved=True)

            return f"Published! (msg #{msg_id})"
        except Exception:
            logger.exception("approve_publish_error", post_id=post_id)
            return "Failed to publish."


async def handle_reject(
    post_id: int,
    session_maker: async_sessionmaker[AsyncSession],
    reason: str | None = None,
) -> str:
    """Reject a post."""
    from sqlalchemy import select

    from app.agent.channel.source_manager import update_source_relevance

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status == "rejected":
            return "Already rejected."
        if post.status == "approved":
            return "Already published — cannot reject."

        source_urls = await _extract_source_urls(post)
        post.reject(reason)
        await session.commit()
        logger.info("post_rejected", post_id=post_id)

        # Penalize relevance of contributing sources
        if source_urls:
            await update_source_relevance(session_maker, source_urls, approved=False)

        return "Post rejected."


async def handle_edit_request(
    bot: Bot,
    post_id: int,
    instruction: str,
    api_key: str,
    model: str,
    review_chat_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    http_timeout: int = 30,
    temperature: float = 0.3,
) -> str:
    """Edit a post based on admin instruction. Updates the review message."""
    from sqlalchemy import select

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status == "approved":
            return "Already published — cannot edit."
        if post.status == "rejected":
            return "Post was rejected — cannot edit."

        # Ask LLM to edit
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
                            f"- ALWAYS end with the Konnekt footer:\n  {KONNEKT_FOOTER}"
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
                return "Edit failed."

            # Ensure footer is present
            if KONNEKT_FOOTER not in new_text:
                new_text = new_text.rstrip() + "\n\n" + KONNEKT_FOOTER

            # Hard-truncate if still over 900
            if len(new_text) > 900:
                max_body = 900 - len("\n\n") - len(KONNEKT_FOOTER)
                body = new_text.replace(KONNEKT_FOOTER, "").rstrip()
                body = body[:max_body].rstrip()
                new_text = body + "\n\n" + KONNEKT_FOOTER

            post.update_text(new_text)

            # Update review message
            if post.review_message_id:
                keyboard = _build_review_keyboard(post_id)
                try:
                    review_plain, review_entities = md_to_entities(
                        _format_review_message(new_text),
                    )
                    await bot.edit_message_text(
                        chat_id=review_chat_id,
                        message_id=post.review_message_id,
                        text=review_plain,
                        entities=review_entities,
                        reply_markup=keyboard,
                    )
                except Exception:
                    logger.exception("review_update_error")

            await session.commit()
            logger.info("post_edited", post_id=post_id, instruction=instruction[:60])
            return "Post updated."

        except Exception:
            logger.exception("edit_error", post_id=post_id)
            return "Edit failed."


async def handle_regen(
    bot: Bot,
    post_id: int,
    api_key: str,
    model: str,
    language: str,
    review_chat_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Regenerate a post from its original sources."""
    from sqlalchemy import select

    from app.agent.channel.generator import generate_post
    from app.agent.channel.sources import ContentItem

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status == "approved":
            return "Already published — cannot regenerate."
        if post.status == "rejected":
            return "Post was rejected — cannot regenerate."

        # Rebuild ContentItems from stored source data
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
            return "No source data to regenerate from."

        new_post = await generate_post(items, api_key=api_key, model=model, language=language)
        if not new_post:
            return "Regeneration failed."

        post.update_text(new_post.text)

        # Update review message
        if post.review_message_id:
            keyboard = _build_review_keyboard(post_id)
            try:
                regen_plain, regen_entities = md_to_entities(
                    _format_review_message(new_post.text),
                )
                await bot.edit_message_text(
                    chat_id=review_chat_id,
                    message_id=post.review_message_id,
                    text=regen_plain,
                    entities=regen_entities,
                    reply_markup=keyboard,
                )
            except Exception:
                logger.exception("review_update_error")

        await session.commit()
        logger.info("post_regenerated", post_id=post_id)
        return "Post regenerated."
