"""Outgoing-only ``aiogram.Bot`` for the web admin process.

Creates an HTTP client to Telegram's Bot API for actions originated by the
admin UI (approve → publish, future: ban / unban). No dispatcher, no
``get_updates`` long-poll: only the in-process bot runs that loop. Multiple
processes can call the same outgoing endpoints — Telegram doesn't care.

Mirrors the moderator bot's defaults (``parse_mode='HTML'``) so message
formatting is consistent regardless of which process sent it.
"""

from __future__ import annotations

import contextlib

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webapi.publish_bot")


def build_publish_bot() -> Bot:
    """Construct the outgoing-only Bot. Caller is responsible for ``close()``."""
    return Bot(
        token=settings.telegram.token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )


async def close_publish_bot(bot: Bot) -> None:
    with contextlib.suppress(Exception):
        await bot.session.close()
        logger.info("publish_bot_closed")
