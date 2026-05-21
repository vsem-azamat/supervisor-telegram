from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import types
from app.core.config import settings
from app.presentation.telegram.handlers.ad_review import process_ad_review
from app.presentation.telegram.utils.callback_data import AdReviewAction
from sqlalchemy.ext.asyncio import AsyncSession

MOD_CHAT = -100999


def _callback(chat_id: int) -> AsyncMock:
    """A CallbackQuery whose `message` lives in chat `chat_id`."""
    message = AsyncMock(spec=types.Message)
    message.chat = SimpleNamespace(id=chat_id)
    message.html_text = "📢 Похоже на рекламу"
    message.text = "📢 Похоже на рекламу"
    # Explicitly set coroutine methods as AsyncMock so awaitable assertions work.
    message.edit_reply_markup = AsyncMock()
    message.edit_text = AsyncMock()
    callback = AsyncMock()
    callback.message = message
    return callback


async def test_ignores_callback_from_other_chat(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=-1001)  # not the moderator chat
    data = AdReviewAction(action="skip", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_reply_markup.assert_not_awaited()
    callback.answer.assert_awaited()


async def test_skip_finalizes_alert(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=MOD_CHAT)
    data = AdReviewAction(action="skip", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_reply_markup.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited()


async def test_already_handled_when_claim_fails(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=MOD_CHAT)
    callback.message.edit_reply_markup.side_effect = RuntimeError("message is not modified")
    data = AdReviewAction(action="skip", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_with("Уже обработано")


async def test_delete_delegates_to_apply_ad_decision(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=MOD_CHAT)
    decision = AsyncMock(return_value="🗑 <b>Удалено.</b>")
    monkeypatch.setattr("app.presentation.telegram.handlers.ad_review.apply_ad_decision", decision)
    bot = AsyncMock()
    data = AdReviewAction(action="delete", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, bot, session)

    decision.assert_awaited_once_with(bot, session, action="delete", chat_id=-1001, message_id=11, user_id=777)
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_with("Готово")


async def test_decision_error_is_finalized(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", MOD_CHAT)
    callback = _callback(chat_id=MOD_CHAT)
    decision = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr("app.presentation.telegram.handlers.ad_review.apply_ad_decision", decision)
    data = AdReviewAction(action="ban", chat_id=-1001, message_id=11, user_id=777)

    await process_ad_review(callback, data, AsyncMock(), session)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_with("Ошибка")
