"""Hiding Telegram's join and leave notices.

A chat that sees a message a week fills up with them, and a wall of "X joined"
reads as a dead room. The notice goes; the membership does not — the member list
is unchanged, the bot still records the event, and a welcome message, where one
is configured, is still posted.

The setting is on by default, including for chats that already exist, because
every deployment has this problem before it has any other.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage
from app.db.models import Chat
from app.presentation.telegram.handlers.events import remove_membership_notice

pytestmark = pytest.mark.unit

CHAT_ID = -1001192822531


class _Notice:
    """Only what the handler touches: which chat, and the ability to be deleted."""

    def __init__(self, chat_id: int = CHAT_ID) -> None:
        self.chat = type("Chat", (), {"id": chat_id})()
        self.delete = AsyncMock()


async def _chat(session, **kwargs) -> Chat:
    chat = Chat(id=CHAT_ID, title="Karlova univerzita", resource_status=Chat.STATUS_APPROVED, **kwargs)
    session.add(chat)
    await session.commit()
    return chat


class TestWhenItRemovesTheNotice:
    async def test_a_new_chat_is_tidied_without_being_asked(self, session) -> None:
        """Default on: the setting exists to turn it off, not to turn it on."""
        await _chat(session)
        notice = _Notice()

        await remove_membership_notice(notice, session)

        notice.delete.assert_awaited_once()

    async def test_a_chat_that_opted_out_keeps_its_notices(self, session) -> None:
        await _chat(session, is_service_cleanup_enabled=False)
        notice = _Notice()

        await remove_membership_notice(notice, session)

        notice.delete.assert_not_awaited()

    async def test_an_unknown_chat_is_left_alone(self, session) -> None:
        """No row means the bot has no business acting there yet."""
        notice = _Notice(chat_id=-1009999999999)

        await remove_membership_notice(notice, session)

        notice.delete.assert_not_awaited()


class TestWhenTelegramRefuses:
    async def test_a_refusal_does_not_reach_the_caller(self, session) -> None:
        """Missing rights, or a notice too old to delete. The chat is noisier; nothing broke."""
        await _chat(session)
        notice = _Notice()
        refusal = TelegramBadRequest(method=DeleteMessage(chat_id=CHAT_ID, message_id=1), message="can't be deleted")
        notice.delete = AsyncMock(side_effect=refusal)

        await remove_membership_notice(notice, session)

        notice.delete.assert_awaited_once()


class TestTheDefault:
    def test_a_chat_created_today_has_it_on(self) -> None:
        assert Chat(id=CHAT_ID).is_service_cleanup_enabled is True

    def test_it_can_be_turned_off_at_construction(self) -> None:
        assert Chat(id=CHAT_ID, is_service_cleanup_enabled=False).is_service_cleanup_enabled is False
