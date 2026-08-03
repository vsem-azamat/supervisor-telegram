"""What lands in the report chat when a member complains."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message, User
from app.moderation import report


def _user(id_: int, first: str, username: str | None = None) -> User:
    return User(id=id_, is_bot=False, first_name=first, username=username)


def _message(text: str, *, chat: Chat | None = None, message_id: int = 456) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=chat or Chat(id=-1001234567890, type="supergroup", title="Test Chat", username="testchat"),
        from_user=_user(987654321, "Jane", "reported"),
        text=text,
    )


async def _send(message: Message, *, reporter: User | None = None) -> str:
    """Run the service against a stub bot and hand back the text it sent."""
    bot = AsyncMock()
    with patch("app.moderation.report.settings") as settings:
        settings.admin.default_report_chat_id = -100999
        await report.report_to_moderators(
            bot,
            reporter or _user(123456789, "John", "reporter"),
            _user(987654321, "Jane", "reported"),
            message,
        )
    return bot.send_message.call_args[1]["text"]


@pytest.mark.unit
class TestTheSummary:
    async def test_carries_the_reported_text(self):
        assert "Купите диплом" in await _send(_message("Купите диплом"))

    async def test_carries_the_target_id(self):
        """A name is not enough to act on — two people share one."""
        assert "987654321" in await _send(_message("что угодно"))

    async def test_links_back_to_the_message(self):
        text = await _send(_message("что угодно"))
        assert "https://t.me/testchat/456" in text

    async def test_links_back_without_a_username(self):
        """Private supergroups need the /c/ form, and most of ours are private."""
        private = Chat(id=-1001234567890, type="supergroup", title="Закрытый")
        text = await _send(_message("что угодно", chat=private))
        assert "https://t.me/c/1234567890/456" in text

    async def test_a_long_message_is_cut(self):
        text = await _send(_message("я" * 900))
        assert "…" in text
        assert "я" * 900 not in text

    async def test_goes_to_the_report_chat(self):
        bot = AsyncMock()
        with patch("app.moderation.report.settings") as settings:
            settings.admin.default_report_chat_id = -100999
            await report.report_to_moderators(bot, _user(1, "A"), _user(2, "B"), _message("hi"))
        assert bot.send_message.call_args[1]["chat_id"] == -100999


@pytest.mark.unit
class TestTheReportedTextIsNotTrusted:
    """It is written by the person somebody is complaining about.

    The summary is read by administrators inside Telegram, which renders the
    HTML the bot sends. Markup surviving out of the quoted message would let the
    subject of a complaint write the report about themselves.
    """

    async def test_tags_are_escaped(self):
        text = await _send(_message("<b>админ</b> сказал что всё ок"))
        assert "&lt;b&gt;" in text
        assert "<b>админ</b>" not in text

    async def test_an_injected_link_stays_text(self):
        text = await _send(_message('<a href="https://evil.example">жми</a>'))
        assert '<a href="https://evil.example">' not in text


@pytest.mark.unit
class TestWhenTelegramRefuses:
    async def test_a_failed_send_does_not_raise(self):
        """The member is already being thanked; an exception here would surface
        to them as a failure they cannot do anything about."""
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("chat not found")
        with patch("app.moderation.report.settings") as settings:
            settings.admin.default_report_chat_id = -100999
            await report.report_to_moderators(bot, _user(1, "A"), _user(2, "B"), _message("hi"))
