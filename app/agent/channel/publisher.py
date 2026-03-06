"""Channel publisher — sends generated posts to Telegram channels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InputMediaPhoto, URLInputFile

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

    from app.agent.channel.generator import GeneratedPost

logger = get_logger("channel.publisher")


async def publish_post(bot: Bot, channel_id: int | str, post: GeneratedPost) -> int | None:
    """Publish a post to a Telegram channel. Returns message_id on success.

    Sends as:
    - Media group (album) if multiple images
    - Single photo with caption if one image and text <= 1024
    - Photo + text reply if one image and text > 1024
    - Text message if no images
    """
    images = post.image_urls or ([post.image_url] if post.image_url else [])

    if len(images) > 1:
        msg_id = await _send_media_group(bot, channel_id, post, images)
        if msg_id:
            return msg_id
        logger.warning("media_group_failed_fallback", channel_id=channel_id)

    if images:
        msg_id = await _send_photo_post(bot, channel_id, post, images[0])
        if msg_id:
            return msg_id
        logger.warning("photo_send_failed_fallback_to_text", channel_id=channel_id)

    return await _send_text_post(bot, channel_id, post)


async def _send_media_group(bot: Bot, channel_id: int | str, post: GeneratedPost, image_urls: list[str]) -> int | None:
    """Send post as a media group (album) — caption on first photo."""
    try:
        media = []
        for i, url in enumerate(image_urls[:10]):  # Telegram max 10 per group
            photo = URLInputFile(url)
            if i == 0 and len(post.text) <= 1024:
                media.append(InputMediaPhoto(media=photo, caption=post.text, parse_mode="HTML"))
            else:
                media.append(InputMediaPhoto(media=photo))

        messages = await bot.send_media_group(chat_id=channel_id, media=media)

        # If caption was too long, send text separately as reply
        if len(post.text) > 1024 and messages:
            text_msg = await bot.send_message(
                chat_id=channel_id,
                text=post.text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_to_message_id=messages[0].message_id,
            )
            logger.info(
                "media_group_published",
                channel_id=channel_id,
                photos=len(messages),
                text_msg=text_msg.message_id,
            )
            return text_msg.message_id

        if messages:
            logger.info(
                "media_group_published",
                channel_id=channel_id,
                photos=len(messages),
                message_id=messages[0].message_id,
            )
            return messages[0].message_id
        return None
    except Exception:
        logger.exception("media_group_error", channel_id=channel_id)
        return None


async def _send_photo_post(bot: Bot, channel_id: int | str, post: GeneratedPost, image_url: str) -> int | None:
    """Send post as a single photo with caption."""
    try:
        photo = URLInputFile(image_url)
        if len(post.text) <= 1024:
            msg = await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=post.text,
                parse_mode="HTML",
            )
        else:
            photo_msg = await bot.send_photo(chat_id=channel_id, photo=photo)
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
