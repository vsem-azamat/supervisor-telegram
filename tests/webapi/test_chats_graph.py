"""Tests for /api/chats/graph tree endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Chat
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


async def _seed(session_maker, chats: list[tuple[int, str | None, int | None]]) -> None:
    async with session_maker() as session:
        for chat_id, title, parent_id in chats:
            session.add(Chat(id=chat_id, title=title, parent_chat_id=parent_id))
        await session.commit()


async def test_graph_empty_db_returns_empty_list(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/chats/graph")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_graph_one_root_two_children(client_factory, db_session_maker) -> None:
    await _seed(
        db_session_maker,
        [
            (-100, "ČVUT", None),
            (-101, "FEL", -100),
            (-102, "FIT", -100),
        ],
    )

    async with client_factory() as client:
        resp = await client.get("/api/chats/graph")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    root = body[0]
    assert root["id"] == -100
    child_ids = sorted(c["id"] for c in root["children"])
    assert child_ids == [-102, -101]
    for c in root["children"]:
        assert c["children"] == []


async def test_graph_orphan_becomes_root(client_factory, db_session_maker) -> None:
    # parent_chat_id points to a chat that doesn't exist in the table
    await _seed(db_session_maker, [(-101, "Orphan", -999)])

    async with client_factory() as client:
        resp = await client.get("/api/chats/graph")

    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == -101


async def test_graph_self_loop_treated_as_root(client_factory, db_session_maker) -> None:
    await _seed(db_session_maker, [(-200, "SelfRef", -200)])

    async with client_factory() as client:
        resp = await client.get("/api/chats/graph")

    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == -200
    assert body[0]["children"] == []


async def test_graph_three_levels_nested(client_factory, db_session_maker) -> None:
    await _seed(
        db_session_maker,
        [
            (-1, "Uni", None),
            (-2, "Faculty", -1),
            (-3, "Department", -2),
        ],
    )

    async with client_factory() as client:
        resp = await client.get("/api/chats/graph")

    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == -1
    assert len(body[0]["children"]) == 1
    assert body[0]["children"][0]["id"] == -2
    assert len(body[0]["children"][0]["children"]) == 1
    assert body[0]["children"][0]["children"][0]["id"] == -3
