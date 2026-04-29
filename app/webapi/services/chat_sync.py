"""Helpers for refreshing Chat metadata + photo from Telegram on demand.

Two paths share these helpers:
* The background snapshot loop (``snapshot_loop.snapshot_once``) calls
  them on its hourly tick.
* The manual ``POST /api/chats/{id}/refresh`` endpoint calls them when
  the admin clicks "Refresh from Telegram" in the web UI.

Title sync uses the Telethon-fed ``ChatInfo`` already in scope. Photo sync
goes through the Bot API (``getChat`` returns ``photo.big_file_id``) — the
moderator bot is already a member of every managed chat, so this is the
right tool. Telethon's ``download_profile_photo`` is byte-only and would
require a re-upload to obtain a Bot-API file_id; not worth the complexity
for the marginal coverage of chats the bot somehow can't see.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest

from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

logger = get_logger("webapi.chat_sync")


async def fetch_chat_photo_file_id(*, bot: Bot, chat_id: int) -> str | None:
    """Bot API ``getChat`` → ``chat.photo.big_file_id``.

    Returns None when the chat has no photo, the bot can't see it, or any
    Telegram error occurs. The caller decides whether to keep the previous
    cached file_id or NULL it out.
    """
    try:
        chat = await bot.get_chat(chat_id)
    except TelegramBadRequest as e:
        logger.warning("get_chat failed", chat_id=chat_id, error=str(e))
        return None
    photo = getattr(chat, "photo", None)
    if photo is None:
        return None
    return getattr(photo, "big_file_id", None)
