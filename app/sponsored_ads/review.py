"""Detect ad blasts and alert moderators with action buttons."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.text import escape_html
from app.core.time import utc_now
from app.db.models import Message
from app.presentation.telegram.utils.callback_data import AdReviewAction
from app.sponsored_ads.text import normalize_text

if TYPE_CHECKING:
    from aiogram import Bot, types
    from aiogram.types import InlineKeyboardMarkup
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("sponsored_ads.review")

_SNIPPET_CHARS = 300


async def should_send_alert(
    db: AsyncSession,
    *,
    user_id: int,
    text: str | None,
    window_hours: int = 24,
) -> bool:
    """False when this (user, text) blast was already alerted within the window.

    The current message is already saved in `messages` by the time this runs,
    so exactly one match is the current message itself; two or more means an
    earlier copy exists and an alert was already sent for it.
    """
    if not text:
        return False
    target = normalize_text(text)
    cutoff = utc_now() - datetime.timedelta(hours=window_hours)
    rows = (
        (
            await db.execute(
                select(Message.message).where(
                    Message.user_id == user_id,
                    Message.timestamp >= cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    matches = sum(1 for m in rows if m and normalize_text(m) == target)
    return matches <= 1


def build_alert_text(*, chat_title: str | None, user: types.User, snippet: str) -> str:
    """HTML alert body shown to moderators."""
    mention = user.mention_html()
    chat = escape_html(chat_title or "—")
    body = escape_html(snippet[:_SNIPPET_CHARS])
    return (
        "📢 <b>Похоже на рекламу</b>\n"
        f"Чат: {chat}\n"
        f"Автор: {mention} (<code>{user.id}</code>)\n\n"
        f"<blockquote>{body}</blockquote>"
    )


def build_alert_keyboard(*, chat_id: int, message_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Three-button keyboard: skip / delete / ban."""
    builder = InlineKeyboardBuilder()
    for text, action in (("⏭ Пропустить", "skip"), ("🗑 Удалить", "delete"), ("🚫 Бан", "ban")):
        builder.button(
            text=text,
            callback_data=AdReviewAction(action=action, chat_id=chat_id, message_id=message_id, user_id=user_id),
        )
    builder.adjust(3)
    return builder.as_markup()


async def notify_moderators(bot: Bot, db: AsyncSession, message: types.Message) -> None:
    """Send a moderator alert for a freshly-detected ad message.

    No-op when the feature is disabled, no moderator chat is configured, the
    message has no author, or this blast was already alerted.
    """
    cfg = settings.sponsored_ads
    if not cfg.enabled or not cfg.moderator_chat_id:
        return
    user = message.from_user
    if user is None:
        return
    text = message.text or message.caption
    if not await should_send_alert(db, user_id=user.id, text=text):
        return

    alert = build_alert_text(chat_title=message.chat.title, user=user, snippet=text or "")
    keyboard = build_alert_keyboard(
        chat_id=message.chat.id,
        message_id=message.message_id,
        user_id=user.id,
    )
    try:
        await bot.send_message(
            cfg.moderator_chat_id,
            alert,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as err:
        logger.error("ad_alert_send_failed", error=str(err), chat_id=cfg.moderator_chat_id)
