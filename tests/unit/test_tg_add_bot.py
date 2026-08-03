"""Restoring the bot writes to real chats and deletes messages, so both are pinned.

Deleting is the part to be careful about. The script clears the "X added Y"
notices its own work produces, and the way that goes wrong is deleting something
a person wrote. So the filter is tested against the shapes it will meet, and the
absent capabilities are read off the syntax tree.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "tg_add_bot.py"


def _identifiers() -> set[str]:
    tree = ast.parse(_PATH.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


_NAMES = _identifiers()


def _load():
    spec = importlib.util.spec_from_file_location("tg_add_bot", _PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tg_add_bot"] = module
    spec.loader.exec_module(module)
    return module


tg_add_bot = _load()
telethon = pytest.importorskip("telethon")

from telethon.tl.types import (  # noqa: E402
    MessageActionChatAddUser,
    MessageActionChatDeleteUser,
    MessageActionChatJoinedByLink,
    MessageService,
)

BOT = 5145935834
WORK = 7764554261
STRANGER = 111222333


def _service(action) -> MessageService:
    return MessageService(id=1, peer_id=None, date=None, action=action)


class TestWhatItDeletes:
    def test_it_deletes_the_notice_that_the_bot_was_added(self) -> None:
        message = _service(MessageActionChatAddUser(users=[BOT]))

        assert tg_add_bot.announces(message, {BOT, WORK}) is True

    def test_it_deletes_the_notice_that_the_work_account_joined_by_link(self) -> None:
        message = _service(MessageActionChatJoinedByLink(inviter_id=1))
        message.from_id = SimpleNamespace(user_id=WORK)

        assert tg_add_bot.announces(message, {BOT, WORK}) is True

    def test_somebody_else_joining_is_left_alone(self) -> None:
        """Students join these chats constantly. None of that is ours to remove."""
        message = _service(MessageActionChatAddUser(users=[STRANGER]))

        assert tg_add_bot.announces(message, {BOT, WORK}) is False

    def test_a_departure_notice_is_left_alone(self) -> None:
        message = _service(MessageActionChatDeleteUser(user_id=BOT))

        assert tg_add_bot.announces(message, {BOT, WORK}) is False

    def test_an_ordinary_message_is_never_a_candidate(self) -> None:
        """The one that matters: what a person wrote is not touched."""
        written = SimpleNamespace(id=7, message="кто-нибудь сдал матан?", action=None)

        assert tg_add_bot.announces(written, {BOT, WORK}) is False


class TestBotRights:
    def test_the_bot_cannot_appoint_administrators(self) -> None:
        """Otherwise a leaked bot token becomes a way to take over the chat."""
        assert tg_add_bot.bot_rights()["add_admins"] is False

    def test_the_bot_cannot_rename_the_chat(self) -> None:
        assert tg_add_bot.bot_rights()["change_info"] is False

    def test_the_bot_can_do_what_its_commands_need(self) -> None:
        rights = tg_add_bot.bot_rights()

        assert rights["delete_messages"] is True
        assert rights["ban_users"] is True
        assert rights["pin_messages"] is True

    def test_the_bot_can_answer_join_requests(self) -> None:
        """Approving one counts as inviting, which is the right it needs."""
        assert tg_add_bot.bot_rights()["invite_users"] is True

    def test_moderation_is_not_anonymous(self) -> None:
        assert tg_add_bot.bot_rights()["anonymous"] is False


class TestItNeverTakesAnythingAway:
    @pytest.mark.parametrize(
        "call",
        ["EditCreatorRequest", "EditBannedRequest", "DeleteParticipantRequest", "LeaveChannelRequest"],
    )
    def test_no_call_that_removes_a_person_or_the_chat(self, call: str) -> None:
        assert call not in _NAMES

    def test_the_only_deletion_is_of_messages(self) -> None:
        assert "delete_messages" in _NAMES


class TestPacing:
    def test_there_is_always_a_pause_between_writes(self) -> None:
        assert tg_add_bot.MIN_DELAY > 0
        assert tg_add_bot.MAX_DELAY > tg_add_bot.MIN_DELAY


class TestApprovedJoinRequests:
    """The notice a chat with join approval produces, and the easy one to miss.

    Most of these chats vet applicants, so an approved join is recorded as
    `JoinedByRequest` rather than as an addition. A filter without it clears a
    handful of notices and leaves the actual pile in place.
    """

    def test_an_approved_join_by_the_bot_is_a_notice(self) -> None:
        from telethon.tl.types import MessageActionChatJoinedByRequest

        message = _service(MessageActionChatJoinedByRequest())
        message.from_id = SimpleNamespace(user_id=BOT)

        assert tg_add_bot.announces(message, {BOT, WORK}) is True

    def test_a_student_approved_into_the_chat_is_left_alone(self) -> None:
        from telethon.tl.types import MessageActionChatJoinedByRequest

        message = _service(MessageActionChatJoinedByRequest())
        message.from_id = SimpleNamespace(user_id=STRANGER)

        assert tg_add_bot.announces(message, {BOT, WORK}) is False
