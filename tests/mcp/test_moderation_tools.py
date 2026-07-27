"""What a leaked MCP token can and cannot do.

The bounded writes act on the call; the removals only ever queue a request for
a human. These tests are the boundary, since the boundary is no longer "which
tools exist".
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import settings
from app.core.enums import PendingActionStatus
from app.db.models import Chat, PendingAction, User
from app.mcp.server import build_mcp_server
from sqlalchemy import select

pytestmark = pytest.mark.asyncio

CHAT_ID = -1001234
UNMANAGED_CHAT_ID = -1009999
USER_ID = 4242
ADMIN_ID = 555


@pytest.fixture
def bot() -> MagicMock:
    tg_bot = MagicMock()
    tg_bot.restrict_chat_member = AsyncMock()
    tg_bot.unban_chat_member = AsyncMock()
    tg_bot.ban_chat_member = AsyncMock()
    tg_bot.send_message = AsyncMock(return_value=MagicMock(message_id=7))
    return tg_bot


@pytest.fixture
def wired(db_session_maker, monkeypatch, bot):
    """Point the tools at the test database and a fake moderator bot."""
    from app.core import container as container_module
    from app.db import session as session_module

    monkeypatch.setattr(session_module, "create_session_maker", lambda: db_session_maker)
    monkeypatch.setattr(container_module.container, "try_get_bot", lambda: bot)
    monkeypatch.setattr(settings.mcp, "initiator_id", ADMIN_ID)
    return db_session_maker


async def _seed_chat(session_maker) -> None:
    async with session_maker() as session:
        session.add(Chat(id=CHAT_ID, title="Managed", resource_status=Chat.STATUS_APPROVED))
        await session.commit()


async def _call(tool: str, args: dict | None = None):
    from fastmcp import Client

    async with Client(build_mcp_server()) as client:
        return (await client.call_tool(tool, args or {})).data


class TestChatScope:
    async def test_mute_refuses_an_unmanaged_chat(self, wired, bot) -> None:
        await _seed_chat(wired)

        result = await _call("mute_user", {"chat_id": UNMANAGED_CHAT_ID, "user_id": USER_ID})

        assert result["error"] == "unknown_chat"
        bot.restrict_chat_member.assert_not_awaited()

    async def test_proposing_a_ban_refuses_an_unmanaged_chat(self, wired, bot) -> None:
        await _seed_chat(wired)

        result = await _call("propose_ban", {"chat_id": UNMANAGED_CHAT_ID, "user_id": USER_ID})

        assert result["error"] == "unknown_chat"
        bot.send_message.assert_not_awaited()

    @pytest.mark.parametrize("status", [Chat.STATUS_DISCOVERED, Chat.STATUS_DISABLED])
    async def test_no_public_action_in_a_chat_awaiting_approval(self, wired, bot, status) -> None:
        """Reading an unapproved chat is fine; acting in one is not.

        Being in the chats table is enough to look, not enough to act — the
        same line the approval gate draws for updates arriving from Telegram.
        """
        async with wired() as session:
            session.add(Chat(id=CHAT_ID, title="Not yet ours", resource_status=status))
            await session.commit()

        result = await _call("mute_user", {"chat_id": CHAT_ID, "user_id": USER_ID})

        assert result["error"] == "chat_not_approved"
        bot.restrict_chat_member.assert_not_awaited()


class TestBoundedWrites:
    async def test_mute_applies_and_is_clamped(self, wired, bot) -> None:
        await _seed_chat(wired)

        result = await _call("mute_user", {"chat_id": CHAT_ID, "user_id": USER_ID, "minutes": 999_999})

        assert result["status"] == "muted"
        assert result["minutes"] == 43200
        bot.restrict_chat_member.assert_awaited_once()

    async def test_mute_also_takes_away_reactions(self, wired, bot) -> None:
        """Bot API 10.0 split reactions out; muting without it leaves them."""
        await _seed_chat(wired)

        await _call("mute_user", {"chat_id": CHAT_ID, "user_id": USER_ID})

        permissions = bot.restrict_chat_member.await_args.kwargs["permissions"]
        assert permissions.can_react_to_messages is False

    async def test_unban_restores_access(self, wired, bot) -> None:
        await _seed_chat(wired)

        result = await _call("unban_user", {"chat_id": CHAT_ID, "user_id": USER_ID})

        assert result["status"] == "unbanned"
        bot.unban_chat_member.assert_awaited_once()


class TestRemovalsWait:
    async def test_propose_ban_bans_nobody(self, wired, bot) -> None:
        await _seed_chat(wired)

        result = await _call("propose_ban", {"chat_id": CHAT_ID, "user_id": USER_ID, "reason": "spam"})

        assert result["status"] == "awaiting_confirmation"
        bot.ban_chat_member.assert_not_awaited()

        async with wired() as session:
            pending = await session.scalar(select(PendingAction).where(PendingAction.id == result["pending_id"]))
        assert pending is not None
        assert pending.status == PendingActionStatus.PENDING
        assert pending.origin == "mcp"
        assert pending.initiator_id == ADMIN_ID

    async def test_propose_blacklist_blacklists_nobody(self, wired, bot) -> None:
        result = await _call("propose_blacklist", {"user_id": USER_ID})

        assert result["status"] == "awaiting_confirmation"
        async with wired() as session:
            blocked = await session.scalar(select(User).where(User.id == USER_ID))
        assert blocked is None

    async def test_proposal_reaches_the_configured_admin(self, wired, bot) -> None:
        await _call("propose_blacklist", {"user_id": USER_ID})

        assert bot.send_message.await_args.kwargs["chat_id"] == ADMIN_ID

    async def test_without_an_initiator_nothing_is_proposed(self, wired, bot, monkeypatch) -> None:
        """Attribution is a precondition, not a nice-to-have on a ban."""
        monkeypatch.setattr(settings.mcp, "initiator_id", 0)

        result = await _call("propose_blacklist", {"user_id": USER_ID})

        assert result["error"] == "initiator_not_configured"
        bot.send_message.assert_not_awaited()
