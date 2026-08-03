"""Banning across every chat, counted in Telegram calls.

The ban itself fans out — one call per chat, which is the whole point. Wiping
the person's messages does not: each message lives in exactly one chat and is
deleted once. Nesting the second inside the first multiplies a hundred deletions
by forty-five chats and spends the rate limit on four and a half thousand calls
that were always going to fail, at the exact moment an administrator is waiting
for a spammer to disappear.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.moderation import blacklist


class _Row:
    def __init__(self, id_: int) -> None:
        self.id = id_


class _Message:
    def __init__(self, chat_id: int, message_id: int) -> None:
        self.chat_id = chat_id
        self.message_id = message_id


@pytest.fixture
def wired(monkeypatch):
    """Three chats, two recorded messages, and repositories that answer."""
    chats = [_Row(-100_1), _Row(-100_2), _Row(-100_3)]
    messages = [_Message(-100_1, 11), _Message(-100_2, 22)]

    user_repo = AsyncMock()
    chat_repo = AsyncMock()
    chat_repo.get_chats.return_value = chats
    message_repo = AsyncMock()
    message_repo.get_user_messages.return_value = messages

    monkeypatch.setattr(blacklist, "UserRepository", MagicMock(return_value=user_repo))
    monkeypatch.setattr(blacklist, "ChatRepository", MagicMock(return_value=chat_repo))
    monkeypatch.setattr(blacklist, "MessageRepository", MagicMock(return_value=message_repo))

    bot = AsyncMock()
    return bot, message_repo


class TestRevokingMessages:
    async def test_each_message_is_deleted_once(self, wired):
        bot, _ = wired

        await blacklist.add_to_blacklist(AsyncMock(), bot, 777, revoke_messages=True)

        assert bot.ban_chat_member.await_count == 3
        assert bot.delete_message.await_count == 2

    async def test_each_message_is_deleted_where_it_lives(self, wired):
        """Not in whichever chat the surrounding loop happened to be on."""
        bot, _ = wired

        await blacklist.add_to_blacklist(AsyncMock(), bot, 777, revoke_messages=True)

        targeted = {(call.kwargs["chat_id"], call.kwargs["message_id"]) for call in bot.delete_message.await_args_list}
        assert targeted == {(-100_1, 11), (-100_2, 22)}

    async def test_the_record_is_read_once(self, wired):
        """Reading it per chat is the same query answered forty-five times."""
        _, message_repo = wired

        await blacklist.add_to_blacklist(AsyncMock(), AsyncMock(), 777, revoke_messages=True)

        assert message_repo.get_user_messages.await_count == 1

    async def test_a_plain_ban_deletes_nothing(self, wired):
        bot, message_repo = wired

        await blacklist.add_to_blacklist(AsyncMock(), bot, 777, revoke_messages=False)

        assert bot.ban_chat_member.await_count == 3
        assert bot.delete_message.await_count == 0
        message_repo.get_user_messages.assert_not_awaited()

    async def test_one_refused_delete_does_not_stop_the_rest(self, wired):
        """Telegram refuses old messages routinely; that is not a reason to stop."""
        bot, _ = wired
        bot.delete_message.side_effect = [Exception("message can't be deleted"), None]

        await blacklist.add_to_blacklist(AsyncMock(), bot, 777, revoke_messages=True)

        assert bot.delete_message.await_count == 2
