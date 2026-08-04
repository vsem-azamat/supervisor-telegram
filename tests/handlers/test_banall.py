"""`/banall` — the one command that removes somebody from every chat at once.

It replaced `!black` and `!spam`, which were two names for nearly the same
thing: both banned everywhere, one also wiped the person's messages, and both
asked for confirmation with a byte-identical dialog. Which of the two you had
run was not recoverable from the screen you were looking at when you pressed
Yes.

So the tests here are mostly about the dialog. The ban itself is old behaviour
and covered where it always was; what is new is that the choice between the two
outcomes is made on a labelled button instead of in the spelling of the command.
"""

from unittest.mock import AsyncMock

import pytest
from app.presentation.telegram.handlers.moderation.blacklist import ban_everywhere
from app.presentation.telegram.utils import BlacklistConfirm

from tests.telegram_helpers import TelegramObjectFactory, create_admin_user, create_normal_user, create_test_chat


@pytest.fixture
def telegram_factory():
    return TelegramObjectFactory()


@pytest.fixture
def message_repo():
    repo = AsyncMock()
    repo.count_user_chats.return_value = 7
    repo.count_user_messages.return_value = 214
    return repo


def _dialog(message) -> tuple[str, list]:
    """The text and the flattened keyboard of whatever the handler answered."""
    text = message.answer.call_args[0][0]
    markup = message.answer.call_args[1]["reply_markup"]
    return text, [button for row in markup.inline_keyboard for button in row]


@pytest.mark.handlers
class TestTheDialog:
    async def test_offers_ban_wipe_and_cancel(self, telegram_factory, message_repo, monkeypatch):
        """Three buttons, and the destructive extra is named on its own."""
        monkeypatch.setattr(
            "app.presentation.telegram.handlers.moderation.blacklist.spam_service.detect_spam",
            AsyncMock(return_value=False),
        )
        chat = create_test_chat()
        target = telegram_factory.create_message(user=create_normal_user(id=777, username="spammer"), chat=chat)
        command = telegram_factory.create_command_message(
            command="banall", user=create_admin_user(), chat=chat, reply_to_message=target
        )

        await ban_everywhere(command, message_repo, AsyncMock())

        _, buttons = _dialog(command)
        assert len(buttons) == 3
        assert buttons[0].text == "Забанить везде"
        assert "стереть" in buttons[1].text.lower()
        assert buttons[2].text == "Отмена"

    async def test_the_two_bans_differ_in_what_they_carry(self, telegram_factory, message_repo, monkeypatch):
        """The whole point: the outcome rides on the button, not on the spelling.

        `!black` and `!spam` sent the same dialog and differed only in the flags
        packed into the callback. Now both flag sets are on screen at once.
        """
        monkeypatch.setattr(
            "app.presentation.telegram.handlers.moderation.blacklist.spam_service.detect_spam",
            AsyncMock(return_value=True),
        )
        chat = create_test_chat()
        target = telegram_factory.create_message(user=create_normal_user(id=777), chat=chat)
        command = telegram_factory.create_command_message(
            command="banall", user=create_admin_user(), chat=chat, reply_to_message=target
        )

        await ban_everywhere(command, message_repo, AsyncMock())

        _, buttons = _dialog(command)
        plain = BlacklistConfirm.unpack(buttons[0].callback_data)
        wipe = BlacklistConfirm.unpack(buttons[1].callback_data)
        assert (plain.revoke, plain.mark_spam) == (0, 0)
        assert (wipe.revoke, wipe.mark_spam) == (1, 1)
        assert plain.user_id == wipe.user_id == 777

    async def test_says_how_many_messages_would_go(self, telegram_factory, message_repo, monkeypatch):
        """A number nobody can see is a number nobody weighed."""
        monkeypatch.setattr(
            "app.presentation.telegram.handlers.moderation.blacklist.spam_service.detect_spam",
            AsyncMock(return_value=False),
        )
        chat = create_test_chat()
        target = telegram_factory.create_message(user=create_normal_user(id=777), chat=chat)
        command = telegram_factory.create_command_message(
            command="banall", user=create_admin_user(), chat=chat, reply_to_message=target
        )

        await ban_everywhere(command, message_repo, AsyncMock())

        text, buttons = _dialog(command)
        assert "7" in text
        assert "214" in text
        assert "214" in buttons[1].text

    async def test_reports_the_spam_verdict_either_way(self, telegram_factory, message_repo, monkeypatch):
        """A filter that stayed quiet is information too — it argues against banning."""
        monkeypatch.setattr(
            "app.presentation.telegram.handlers.moderation.blacklist.spam_service.detect_spam",
            AsyncMock(return_value=False),
        )
        chat = create_test_chat()
        target = telegram_factory.create_message(user=create_normal_user(id=777), chat=chat)
        command = telegram_factory.create_command_message(
            command="banall", user=create_admin_user(), chat=chat, reply_to_message=target
        )

        await ban_everywhere(command, message_repo, AsyncMock())

        text, _ = _dialog(command)
        assert "не сработал" in text

    async def test_without_a_reply_it_offers_nothing(self, telegram_factory, message_repo):
        """No target, no buttons — a keyboard here would be a keyboard aimed at nobody."""
        command = telegram_factory.create_command_message(
            command="banall", user=create_admin_user(), chat=create_test_chat()
        )
        command.reply_to_message = None

        await ban_everywhere(command, message_repo, AsyncMock())

        assert command.answer.call_args[1].get("reply_markup") is None
