"""The read toolset's boundaries: what it refuses, and what it never returns.

Two claims carry the weight here. Telethon runs on a user session that can read
any chat the account is in, so every tool that touches it must refuse a chat
absent from the `chats` table — the mock proves the call never happened, not
merely that the answer was empty. And the projections must drop what should not
travel: a Telegram profile's phone number, and the free-text rationale behind a
past moderation decision.

No live Telethon: the client is a stub installed on the container, which is also
what a deployment without a session looks like from a tool's point of view.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.db.models import Chat, Message, PendingAction, SpamPing, User
from app.mcp.tools.read import register_read_tools
from app.telethon.telethon_client import ChatInfo, ChatMember, MessageInfo, UserInfo

pytestmark = pytest.mark.asyncio

MANAGED_CHAT_ID = -1001234567890
FOREIGN_CHAT_ID = -1009999999999
USER_ID = 555000111
ADMIN_ID = 888000222
PHONE = "+79990001122"


@pytest.fixture
def mcp_session(db_session_maker, monkeypatch):
    """Point the MCP tools at the in-memory test database."""
    from app.db import session as session_module

    monkeypatch.setattr(session_module, "get_session_maker", lambda: db_session_maker)
    return db_session_maker


@pytest.fixture
def telethon_stub(monkeypatch):
    """Install a stand-in Telethon client on the container.

    Every method is an AsyncMock, so a test can assert a call was never made —
    the point of the managed-chat gate.
    """
    from app.core.container import container

    client = SimpleNamespace(
        is_available=True,
        get_chat_history=AsyncMock(return_value=[]),
        search_messages=AsyncMock(return_value=[]),
        get_chat_members=AsyncMock(return_value=[]),
        get_user_info=AsyncMock(return_value=None),
        get_chat_info=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(container, "_telethon_client", client)
    return client


@pytest.fixture
def bot_stub(monkeypatch):
    """Install a stand-in moderator bot on the container."""
    from app.core.container import container

    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=MANAGED_CHAT_ID,
                title="Managed Chat",
                type="supergroup",
                username="managed",
                description="",
            )
        ),
        get_chat_member_count=AsyncMock(return_value=42),
    )
    monkeypatch.setattr(container, "_bot", bot)
    return bot


def _server():
    """A server carrying only the read toolset — server.py registers it itself."""
    from fastmcp import FastMCP

    mcp: FastMCP[None] = FastMCP(name="read-tools-test", mask_error_details=True)
    register_read_tools(mcp)
    return mcp


async def _call(tool: str, args: dict | None = None):
    from fastmcp import Client

    async with Client(_server()) as client:
        result = await client.call_tool(tool, args or {})
    return result.data


async def _seed_chats(session_maker) -> None:
    async with session_maker() as session:
        session.add(Chat(id=MANAGED_CHAT_ID, title="Managed Chat", resource_status=Chat.STATUS_APPROVED))
        session.add(Chat(id=-100777, title="Seen Once", resource_status=Chat.STATUS_DISCOVERED))
        await session.commit()


async def _seed_blocked_users(session_maker, count: int) -> None:
    async with session_maker() as session:
        for index in range(count):
            session.add(User(id=USER_ID + index, username=f"blocked{index}", blocked=True))
        session.add(User(id=USER_ID + 900, username="innocent", blocked=False))
        await session.commit()


# ── the managed-chat gate ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_chat_history", {}),
        ("search_messages", {"query": "spam"}),
        ("get_chat_members", {}),
    ],
)
async def test_telethon_tools_refuse_a_chat_we_do_not_manage(mcp_session, telethon_stub, tool, args) -> None:
    """A user session can read private chats; only the `chats` table opens one."""
    await _seed_chats(mcp_session)

    data = await _call(tool, {"chat_id": FOREIGN_CHAT_ID, **args})

    assert data["error"] == "unknown_chat"
    telethon_stub.get_chat_history.assert_not_awaited()
    telethon_stub.search_messages.assert_not_awaited()
    telethon_stub.get_chat_members.assert_not_awaited()


async def test_get_chat_info_refuses_a_chat_we_do_not_manage(mcp_session, bot_stub, telethon_stub) -> None:
    await _seed_chats(mcp_session)

    data = await _call("get_chat_info", {"chat_id": FOREIGN_CHAT_ID})

    assert data["error"] == "unknown_chat"
    bot_stub.get_chat.assert_not_awaited()


async def test_managed_chat_history_is_returned(mcp_session, telethon_stub) -> None:
    import datetime

    await _seed_chats(mcp_session)
    telethon_stub.get_chat_history.return_value = [
        MessageInfo(
            message_id=7,
            chat_id=MANAGED_CHAT_ID,
            sender_id=USER_ID,
            text="hello there",
            date=datetime.datetime(2026, 1, 2, 3, 4, tzinfo=datetime.UTC),
        )
    ]

    data = await _call("get_chat_history", {"chat_id": MANAGED_CHAT_ID, "limit": 5})

    assert data["returned"] == 1
    message = data["messages"][0]
    assert message["message_id"] == 7
    assert message["text"] == "hello there"
    assert message["text_truncated"] is False
    assert message["date"].startswith("2026-01-02")


@pytest.mark.parametrize(
    ("tool", "args", "attribute", "expected"),
    [
        ("get_chat_history", {"limit": 999}, "get_chat_history", 100),
        ("search_messages", {"query": "x", "limit": 999}, "search_messages", 50),
        ("get_chat_members", {"limit": 999}, "get_chat_members", 200),
    ],
)
async def test_page_sizes_are_clamped(mcp_session, telethon_stub, tool, args, attribute, expected) -> None:
    """An unbounded page would be a cheap way to pull a whole chat out."""
    await _seed_chats(mcp_session)

    await _call(tool, {"chat_id": MANAGED_CHAT_ID, **args})

    assert getattr(telethon_stub, attribute).await_args.kwargs["limit"] == expected


async def test_telethon_tools_refuse_when_the_session_is_down(mcp_session, telethon_stub) -> None:
    """An empty list would read as 'this chat is quiet' rather than 'nobody looked'."""
    await _seed_chats(mcp_session)
    telethon_stub.is_available = False

    data = await _call("get_chat_members", {"chat_id": MANAGED_CHAT_ID})

    assert data["error"] == "telethon_unavailable"


async def test_chat_members_are_projected(mcp_session, telethon_stub) -> None:
    await _seed_chats(mcp_session)
    telethon_stub.get_chat_members.return_value = [
        ChatMember(user_id=USER_ID, first_name="Ada", last_name=None, username="ada")
    ]

    data = await _call("get_chat_members", {"chat_id": MANAGED_CHAT_ID})

    assert data["members"] == [{"user_id": USER_ID, "username": "ada", "first_name": "Ada", "last_name": ""}]


# ── withheld fields ───────────────────────────────────────────────────────


async def test_get_user_info_never_returns_a_phone_number(mcp_session, telethon_stub) -> None:
    """UserInfo carries `phone`; the projection must not let it through."""
    async with mcp_session() as session:
        session.add(User(id=USER_ID, username="target", first_name="Target", blocked=True))
        await session.commit()
    telethon_stub.get_user_info.return_value = UserInfo(
        user_id=USER_ID,
        first_name="Target",
        username="target",
        phone=PHONE,
        bio="just a bio",
        is_premium=True,
        photo_count=3,
    )

    data = await _call("get_user_info", {"user_id": USER_ID})

    assert "phone" not in data
    assert PHONE not in repr(data)
    assert data["bio"] == "just a bio"
    assert data["is_premium"] is True
    assert data["blocked"] is True
    assert data["known_locally"] is True


async def test_get_user_info_works_for_an_unknown_user(mcp_session, telethon_stub) -> None:
    telethon_stub.get_user_info.return_value = UserInfo(user_id=USER_ID, first_name="Stranger", phone=PHONE)

    data = await _call("get_user_info", {"user_id": USER_ID})

    assert data["known_locally"] is False
    assert data["first_name"] == "Stranger"
    assert PHONE not in repr(data)


async def test_moderation_history_counts_what_the_bot_recorded(mcp_session) -> None:
    """Built from traces the bot actually leaves, not a decision log it stopped keeping."""
    import datetime

    from app.core.time import utc_now

    async with mcp_session() as session:
        session.add(Message(chat_id=MANAGED_CHAT_ID, user_id=USER_ID, message_id=1, message="hi"))
        spam = Message(chat_id=MANAGED_CHAT_ID, user_id=USER_ID, message_id=2, message="buy now")
        spam.mark_as_spam()
        session.add(spam)
        session.add(SpamPing(chat_id=MANAGED_CHAT_ID, user_id=USER_ID, message_id=2, kind="link", matches=["t.me/x"]))
        session.add(
            PendingAction(
                origin="mcp",
                initiator_id=1,
                action="ban",
                target_user_id=USER_ID,
                chat_id=MANAGED_CHAT_ID,
                expires_at=utc_now() + datetime.timedelta(minutes=10),
                reason="repeated ads",
            )
        )
        await session.commit()

    data = await _call("get_moderation_history", {"user_id": USER_ID})

    assert data["messages_seen"] == 2
    assert data["messages_marked_spam"] == 1
    assert data["ad_detector_hits"] == 1
    assert data["chats_seen_in"] == 1
    assert [p["action"] for p in data["proposals"]] == ["ban"]
    assert data["proposals"][0]["status"] == "pending"


async def test_moderation_history_shows_what_was_done_to_the_user(mcp_session) -> None:
    """The half that used to be missing: a command typed in a chat left no row."""
    from app.db.models import ModerationEvent

    async with mcp_session() as session:
        session.add(
            ModerationEvent(
                action="mute",
                source="command",
                actor_id=ADMIN_ID,
                target_user_id=USER_ID,
                chat_id=MANAGED_CHAT_ID,
                detail="5 минут",
            )
        )
        await session.commit()

    data = await _call("get_moderation_history", {"user_id": USER_ID})

    (event,) = data["actions_taken"]
    assert (event["action"], event["source"]) == ("mute", "command")
    assert event["actor_id"] == ADMIN_ID
    assert event["detail"] == "5 минут"


async def test_moderation_history_is_empty_for_a_clean_user(mcp_session) -> None:
    data = await _call("get_moderation_history", {"user_id": USER_ID})

    assert data["known_locally"] is False
    assert data["messages_seen"] == 0
    assert data["proposals"] == []


# ── bounded listings ──────────────────────────────────────────────────────


async def test_get_blacklist_respects_limit(mcp_session) -> None:
    """The assistant's version dumped the whole table; this one must not."""
    await _seed_blocked_users(mcp_session, count=5)

    data = await _call("get_blacklist", {"limit": 2})

    assert data["returned"] == 2
    assert len(data["users"]) == 2
    assert data["total"] == 5
    assert all(user["blocked"] for user in data["users"])


async def test_get_blacklist_excludes_unblocked_users(mcp_session) -> None:
    await _seed_blocked_users(mcp_session, count=3)

    data = await _call("get_blacklist")

    assert data["total"] == 3
    assert "innocent" not in [user["username"] for user in data["users"]]


async def test_get_blacklist_limit_is_clamped(mcp_session) -> None:
    await _seed_blocked_users(mcp_session, count=3)

    data = await _call("get_blacklist", {"limit": 100_000})

    assert data["returned"] == 3


async def test_list_chats_reports_resource_status(mcp_session) -> None:
    """A row in `chats` is not an endorsement — the caller must see which is which."""
    await _seed_chats(mcp_session)

    data = await _call("list_chats")

    by_id = {chat["chat_id"]: chat for chat in data["chats"]}
    assert by_id[MANAGED_CHAT_ID]["resource_status"] == Chat.STATUS_APPROVED
    assert by_id[MANAGED_CHAT_ID]["is_approved"] is True
    assert by_id[-100777]["resource_status"] == Chat.STATUS_DISCOVERED
    assert by_id[-100777]["is_approved"] is False
    assert data["total"] == 2


async def test_list_chats_respects_limit(mcp_session) -> None:
    await _seed_chats(mcp_session)

    data = await _call("list_chats", {"limit": 1})

    assert data["returned"] == 1
    assert data["total"] == 2


# ── surface ───────────────────────────────────────────────────────────────


async def test_chat_info_merges_telethon_enrichment(mcp_session, bot_stub, telethon_stub) -> None:
    await _seed_chats(mcp_session)
    telethon_stub.get_chat_info.return_value = ChatInfo(
        chat_id=MANAGED_CHAT_ID,
        title="Managed Chat",
        description="from telethon",
        linked_chat_id=-100555,
    )

    data = await _call("get_chat_info", {"chat_id": MANAGED_CHAT_ID})

    assert data["member_count"] == 42
    assert data["description"] == "from telethon"
    assert data["linked_chat_id"] == -100555
    assert data["resource_status"] == Chat.STATUS_APPROVED


async def test_chat_info_survives_a_failing_enrichment(mcp_session, bot_stub, telethon_stub) -> None:
    """Telethon is a bonus here; losing it must not lose the Bot API answer."""
    await _seed_chats(mcp_session)
    telethon_stub.get_chat_info.side_effect = RuntimeError("session dropped")

    data = await _call("get_chat_info", {"chat_id": MANAGED_CHAT_ID})

    assert data["title"] == "Managed Chat"
    assert data["member_count"] == 42


async def test_toolset_is_read_only(mcp_session) -> None:
    """Pin the exposed surface: nothing here may mutate anything."""
    from fastmcp import Client

    async with Client(_server()) as client:
        names = {tool.name for tool in await client.list_tools()}

    assert names == {
        "list_chats",
        "get_blacklist",
        "get_chat_info",
        "get_user_info",
        "get_moderation_history",
        "get_chat_history",
        "search_messages",
        "get_chat_members",
    }
