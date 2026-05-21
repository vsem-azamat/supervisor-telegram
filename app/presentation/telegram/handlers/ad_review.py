"""Moderator callback handler for flagged-ad alerts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import Bot, Router, types

from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.presentation.telegram.utils.callback_data import AdReviewAction
from app.sponsored_ads.decisions import apply_ad_decision

logger = get_logger("handlers.ad_review")

ad_review_router = Router()


@ad_review_router.callback_query(AdReviewAction.filter())
async def process_ad_review(
    callback: types.CallbackQuery,
    callback_data: AdReviewAction,
    bot: Bot,
    db: AsyncSession,
) -> None:
    """Handle a moderator tapping skip / delete / ban on an ad alert."""
    message = callback.message
    if not isinstance(message, types.Message) or message.chat.id != settings.sponsored_ads.moderator_chat_id:
        await callback.answer()
        return

    # Claim the alert: removing the keyboard fails if another moderator already acted.
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        await callback.answer("Уже обработано")
        return

    base = message.html_text or message.text or "📢 Похоже на рекламу"

    if callback_data.action == "skip":
        await _finalize(message, base, "⏭ <b>Пропущено.</b>")
        await callback.answer("Пропущено")
        return

    try:
        status = await apply_ad_decision(
            bot,
            db,
            action=callback_data.action,
            chat_id=callback_data.chat_id,
            message_id=callback_data.message_id,
            user_id=callback_data.user_id,
        )
    except Exception as err:
        logger.error("ad_decision_failed", error=str(err), action=callback_data.action)
        await _finalize(message, base, "⚠️ <b>Ошибка при обработке.</b>")
        await callback.answer("Ошибка")
        return

    await _finalize(message, base, status)
    await callback.answer("Готово")


async def _finalize(message: types.Message, base: str, status: str) -> None:
    """Rewrite the alert with the final outcome; best-effort."""
    try:
        await message.edit_text(f"{base}\n\n{status}")
    except Exception as err:
        logger.warning("ad_review_finalize_failed", error=str(err))
