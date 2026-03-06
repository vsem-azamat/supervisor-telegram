"""Channel publisher — sends generated posts to Telegram channels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

    from app.agent.channel.generator import GeneratedPost

logger = get_logger("channel.publisher")


async def publish_post(bot: Bot, channel_id: int | str, post: GeneratedPost) -> int | None:
    """Publish a post to a Telegram channel. Returns message_id on success."""
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
