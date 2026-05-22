import datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import types
from app.moderation import spam_service
from app.presentation.telegram.middlewares import history as history_mw
from sqlalchemy.ext.asyncio import AsyncSession


def _update(text: str) -> types.Update:
    return types.Update(
        update_id=1,
        message=types.Message(
            message_id=11,
            date=datetime.datetime(2026, 5, 21),
            chat=types.Chat(id=-1001, type="supergroup", title="Prague Chat"),
            from_user=types.User(id=777, is_bot=False, first_name="Ad"),
            text=text,
        ),
    )


async def test_middleware_triggers_ad_review_on_signal(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spam_service, "detect_spam", AsyncMock(return_value=False))
    spy = AsyncMock()
    monkeypatch.setattr(history_mw.ad_review, "notify_moderators", spy)

    middleware = history_mw.HistoryMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {"db": session, "bot": object()}

    result = await middleware(handler, _update("приходите сюда t.me/spampromo срочно"), data)

    assert result == "ok"
    spy.assert_awaited_once()


async def test_middleware_skips_ad_review_without_signal(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spam_service, "detect_spam", AsyncMock(return_value=False))
    spy = AsyncMock()
    monkeypatch.setattr(history_mw.ad_review, "notify_moderators", spy)

    middleware = history_mw.HistoryMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {"db": session, "bot": object()}

    await middleware(handler, _update("just a normal friendly message"), data)

    spy.assert_not_awaited()


async def test_middleware_swallows_ad_review_failure(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spam_service, "detect_spam", AsyncMock(return_value=False))
    spy = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(history_mw.ad_review, "notify_moderators", spy)

    middleware = history_mw.HistoryMiddleware()
    handler = AsyncMock(return_value="ok")
    data = {"db": session, "bot": object()}

    result = await middleware(handler, _update("приходите сюда t.me/spampromo срочно"), data)

    assert result == "ok"  # the raising notify_moderators was swallowed; handler still ran
    spy.assert_awaited_once()
