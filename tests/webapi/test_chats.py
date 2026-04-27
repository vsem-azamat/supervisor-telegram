"""Tests for /api/chats endpoints."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Chat, ChatMemberSnapshot, Message
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session, get_telethon

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    async def _override_get_telethon():
        return None  # no telethon in tests

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_telethon] = _override_get_telethon
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_telethon, None)


async def test_list_chats_returns_all(client_factory, db_session_maker) -> None:
    async with db_session_maker() as session:
        session.add(Chat(id=-1001, title="A"))
        session.add(Chat(id=-1002, title="B"))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/chats")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    titles = sorted(c["title"] for c in body)
    assert titles == ["A", "B"]
    # member_count is None when telethon is absent
    assert all(c["member_count"] is None for c in body)


async def test_chat_detail_heatmap_aggregates_messages(client_factory, db_session_maker) -> None:
    chat_id = -1010
    # Anchor timestamps relative to "now" so they always fall inside the
    # endpoint's 7-day lookback window — fixed dates would expire and break
    # the test once the wall clock moved past them.
    from app.core.time import utc_now

    now = utc_now()
    base = (now - datetime.timedelta(days=2)).replace(hour=10, minute=30, second=0, microsecond=0)
    next_day = (base + datetime.timedelta(days=1)).replace(hour=15, minute=0)

    async with db_session_maker() as session:
        session.add(Chat(id=chat_id, title="C"))
        for i in range(3):
            msg = Message(chat_id=chat_id, user_id=1, message_id=i)
            msg.timestamp = base
            session.add(msg)
        msg = Message(chat_id=chat_id, user_id=1, message_id=99)
        msg.timestamp = next_day
        session.add(msg)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get(f"/api/chats/{chat_id}")

    assert resp.status_code == 200
    body = resp.json()
    cells = {(c["weekday"], c["hour"]): c["count"] for c in body["heatmap"]}
    assert cells.get((base.weekday(), base.hour)) == 3
    assert cells.get((next_day.weekday(), next_day.hour)) == 1


async def test_chat_detail_returns_member_snapshots(client_factory, db_session_maker) -> None:
    chat_id = -1020
    base = datetime.datetime(2026, 4, 21, 12, 0)
    async with db_session_maker() as session:
        session.add(Chat(id=chat_id, title="D"))
        for hours_ago, count in [(72, 100), (48, 110), (24, 120), (0, 125)]:
            captured = base - datetime.timedelta(hours=hours_ago)
            session.add(ChatMemberSnapshot(chat_id=chat_id, member_count=count, captured_at=captured))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get(f"/api/chats/{chat_id}")

    body = resp.json()
    counts = [p["member_count"] for p in body["member_snapshots"]]
    assert counts == [100, 110, 120, 125]  # ascending captured_at


async def test_chat_detail_404(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/chats/999999")
    assert resp.status_code == 404
