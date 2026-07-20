"""Outgoing-only ``aiogram.Bot`` that owns review messages.

A review message carries an inline keyboard, and Telegram delivers a button's
callback to the bot that sent the message. In the bot process
``channel_review_router`` is attached to the assistant dispatcher whenever the
assistant is active, and to the moderator dispatcher otherwise
(``app/presentation/telegram/bot.py``). Any other process that sends a review
message must therefore pick the same identity, or the approve/reject buttons
reach a bot with no handler for them and silently do nothing.

This is deliberately not ``build_publish_bot``: that one is always the moderator
token because publishing to a channel needs no callback handling.
"""

from __future__ import annotations

import contextlib

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webapi.review_bot")


def build_review_bot() -> Bot:
    """Construct the outgoing-only Bot whose identity owns review callbacks.

    Mirrors how each identity is constructed in the bot process: the assistant
    bot runs without a default parse mode so entity-based formatting survives,
    while the moderator bot defaults to HTML.
    """
    if settings.assistant.active:
        return Bot(token=settings.assistant.token)
    return Bot(token=settings.telegram.token, default=DefaultBotProperties(parse_mode="HTML"))


async def close_review_bot(bot: Bot) -> None:
    with contextlib.suppress(Exception):
        await bot.session.close()
