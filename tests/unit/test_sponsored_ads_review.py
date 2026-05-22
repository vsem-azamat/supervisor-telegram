import datetime

import pytest
from aiogram import types
from app.core.config import settings
from app.db.models import Message
from app.presentation.telegram.utils.callback_data import AdReviewAction
from app.sponsored_ads import review
from sqlalchemy.ext.asyncio import AsyncSession


def _user(user_id: int = 777) -> types.User:
    return types.User(id=user_id, is_bot=False, first_name="Ad")


def _message(text: str = "buy now") -> types.Message:
    return types.Message(
        message_id=11,
        date=datetime.datetime(2026, 5, 21),
        chat=types.Chat(id=-1001, type="supergroup", title="Prague Chat"),
        from_user=_user(),
        text=text,
    )


class _StubBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(
        self, chat_id: int, text: str, reply_markup: object = None, disable_web_page_preview: bool = False
    ) -> None:
        self.messages.append((chat_id, text))


async def test_should_send_alert_true_for_first_occurrence(session: AsyncSession) -> None:
    session.add(Message(chat_id=-1001, user_id=777, message_id=11, message="buy now"))
    await session.commit()
    assert await review.should_send_alert(session, user_id=777, text="buy now") is True


async def test_should_send_alert_false_for_repeat_blast(session: AsyncSession) -> None:
    session.add_all(
        [
            Message(chat_id=-1001, user_id=777, message_id=11, message="buy now"),
            Message(chat_id=-1002, user_id=777, message_id=22, message="BUY  now"),
        ]
    )
    await session.commit()
    assert await review.should_send_alert(session, user_id=777, text="buy now") is False


async def test_should_send_alert_false_for_empty_text(session: AsyncSession) -> None:
    assert await review.should_send_alert(session, user_id=777, text=None) is False


def test_build_alert_text_contains_chat_user_and_snippet() -> None:
    text = review.build_alert_text(chat_title="Prague Chat", user=_user(), snippet="Buy cheap stuff")
    assert "Prague Chat" in text
    assert "777" in text
    assert "Buy cheap stuff" in text


def test_build_alert_keyboard_has_three_actions() -> None:
    kb = review.build_alert_keyboard(chat_id=-1001, message_id=11, user_id=777)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    actions = {AdReviewAction.unpack(cb).action for cb in callbacks}
    assert actions == {"skip", "delete", "ban"}


async def test_notify_moderators_sends_alert(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "enabled", True)
    monkeypatch.setattr(settings.sponsored_ads, "moderator_chat_id", -100999)
    session.add(Message(chat_id=-1001, user_id=777, message_id=11, message="buy now"))
    await session.commit()
    bot = _StubBot()

    await review.notify_moderators(bot, session, _message())

    assert len(bot.messages) == 1
    assert bot.messages[0][0] == -100999


async def test_notify_moderators_disabled_is_noop(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "enabled", False)
    bot = _StubBot()
    await review.notify_moderators(bot, session, _message())
    assert bot.messages == []
