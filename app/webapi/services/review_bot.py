"""Outgoing-only ``aiogram.Bot`` that owns review messages.

A review message carries an inline keyboard, and Telegram delivers a button's
callback to the bot that sent the message. ``channel_review_router`` lives on
the moderator dispatcher, so any other process sending a review message must
use the moderator identity — otherwise the approve/reject buttons reach a bot
with no handler for them and silently do nothing.

There used to be a second identity to choose between, and this function existed
to make the choice. It now returns one thing, and survives because its name
records *why* that identity: ``build_publish_bot`` returns the same token for an
unrelated reason, and collapsing the two would lose the distinction the moment a
second identity comes back.
"""

from __future__ import annotations

import contextlib

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webapi.review_bot")


def build_review_bot() -> Bot:
    """Construct the outgoing-only Bot whose identity owns review callbacks."""
    return Bot(token=settings.telegram.token, default=DefaultBotProperties(parse_mode="HTML"))


async def close_review_bot(bot: Bot) -> None:
    with contextlib.suppress(Exception):
        await bot.session.close()
