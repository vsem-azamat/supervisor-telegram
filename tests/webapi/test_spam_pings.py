"""Tests for /api/spam/pings + spam fields on stats/chats endpoints."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Chat, SpamPing
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
        return None

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_telethon] = _override_get_telethon
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_telethon, None)


async def _seed_chat(session_maker, *, chat_id: int = -1001, title: str = "Test") -> None:
    async with session_maker() as session:
        session.add(Chat(id=chat_id, title=title))
        await session.commit()


async def _seed_ping(
    session_maker,
    *,
    chat_id: int = -1001,
    kind: str = "link",
    matches: list[str] | None = None,
    detected_at: datetime.datetime | None = None,
) -> int:
    async with session_maker() as session:
        ping = SpamPing(
            chat_id=chat_id,
            user_id=42,
            message_id=100,
            kind=kind,
            matches=matches or ["t.me/spammer"],
            snippet="check this out",
            detected_at=detected_at,
        )
        session.add(ping)
        await session.commit()
        await session.refresh(ping)
        return ping.id


async def test_list_pings_empty(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/spam/pings")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_pings_returns_newest_first(client_factory, db_session_maker) -> None:
    await _seed_chat(db_session_maker)
    now = datetime.datetime(2026, 4, 21, 10, 0, 0)
    await _seed_ping(db_session_maker, kind="link", detected_at=now)
    await _seed_ping(
        db_session_maker, kind="mention", matches=["@spammer"], detected_at=now + datetime.timedelta(hours=1)
    )

    async with client_factory() as client:
        resp = await client.get("/api/spam/pings")

    body = resp.json()
    assert len(body) == 2
    assert body[0]["kind"] == "mention"  # newest
    assert body[0]["chat_title"] == "Test"
    assert body[1]["kind"] == "link"


async def test_list_pings_filters_by_chat_id(client_factory, db_session_maker) -> None:
    await _seed_chat(db_session_maker, chat_id=-1001, title="A")
    await _seed_chat(db_session_maker, chat_id=-1002, title="B")
    await _seed_ping(db_session_maker, chat_id=-1001)
    await _seed_ping(db_session_maker, chat_id=-1002)

    async with client_factory() as client:
        resp = await client.get("/api/spam/pings", params={"chat_id": -1001})

    body = resp.json()
    assert len(body) == 1
    assert body[0]["chat_id"] == -1001


async def test_list_pings_respects_limit(client_factory, db_session_maker) -> None:
    await _seed_chat(db_session_maker)
    for _ in range(5):
        await _seed_ping(db_session_maker)

    async with client_factory() as client:
        resp = await client.get("/api/spam/pings", params={"limit": 2})

    assert len(resp.json()) == 2


async def test_chat_detail_includes_spam_pings(client_factory, db_session_maker) -> None:
    await _seed_chat(db_session_maker, chat_id=-1001, title="Test")
    await _seed_ping(db_session_maker, chat_id=-1001)

    async with client_factory() as client:
        resp = await client.get("/api/chats/-1001")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["spam_pings"]) == 1
    assert body["spam_pings"][0]["kind"] == "link"
