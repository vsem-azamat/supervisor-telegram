"""Channel publisher — sends generated posts to Telegram channels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import URLInputFile

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

    from app.agent.channel.generator import GeneratedPost

logger = get_logger("channel.publisher")


async def publish_post(bot: Bot, channel_id: int | str, post: GeneratedPost) -> int | None:
    """Publish a post to a Telegram channel. Returns message_id on success.

    Sends as photo with caption if image_url is available, otherwise as text message.
    """
    if post.image_url:
        msg_id = await _send_photo_post(bot, channel_id, post)
        if msg_id:
            return msg_id
        # Fallback to text if photo send fails
        logger.warning("photo_send_failed_fallback_to_text", channel_id=channel_id)

    return await _send_text_post(bot, channel_id, post)


async def _send_photo_post(bot: Bot, channel_id: int | str, post: GeneratedPost) -> int | None:
    """Send post as a photo with caption."""
    try:
        photo = URLInputFile(post.image_url)  # image_url checked by caller
        # Telegram caption limit is 1024 chars; if post is longer, send photo + separate text
        if len(post.text) <= 1024:
            msg = await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=post.text,
                parse_mode="HTML",
            )
        else:
            # Send photo first, then text as reply
            photo_msg = await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
            )
            msg = await bot.send_message(
                chat_id=channel_id,
                text=post.text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_to_message_id=photo_msg.message_id,
            )
        logger.info("photo_post_published", channel_id=channel_id, message_id=msg.message_id)
        return msg.message_id
    except Exception:
        logger.exception("photo_publish_error", channel_id=channel_id)
        return None


async def _send_text_post(bot: Bot, channel_id: int | str, post: GeneratedPost) -> int | None:
    """Send post as plain text message."""
    try:
        msg = await bot.send_message(
            chat_id=channel_id,
            text=post.text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        logger.info("post_published", channel_id=channel_id, message_id=msg.message_id)
        return msg.message_id
    except Exception:
        logger.exception("publish_error", channel_id=channel_id)
        return None
