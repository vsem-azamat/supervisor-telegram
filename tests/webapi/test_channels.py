"""Tests for /api/channels endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Channel, ChannelPost, ChannelSource
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)


async def _seed_channel(session_maker, *, telegram_id: int = -1001, name: str = "C") -> int:
    async with session_maker() as session:
        channel = Channel(telegram_id=telegram_id, name=name, username="c")
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        return channel.id


async def test_list_channels_returns_all(client_factory, db_session_maker) -> None:
    await _seed_channel(db_session_maker, telegram_id=-1001, name="A")
    await _seed_channel(db_session_maker, telegram_id=-1002, name="B")

    async with client_factory() as client:
        resp = await client.get("/api/channels")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = sorted(c["name"] for c in body)
    assert names == ["A", "B"]


async def test_get_channel_detail_includes_sources_and_posts(client_factory, db_session_maker) -> None:
    ch_row_id = await _seed_channel(db_session_maker, telegram_id=-1010, name="D")

    async with db_session_maker() as session:
        session.add(ChannelSource(channel_id=-1010, url="https://x/rss", source_type="rss"))
        session.add(ChannelPost(channel_id=-1010, external_id="e1", title="p1", post_text="x"))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get(f"/api/channels/{ch_row_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ch_row_id
    assert len(body["sources"]) == 1
    assert body["sources"][0]["url"] == "https://x/rss"
    assert len(body["recent_posts"]) == 1
    assert body["recent_posts"][0]["title"] == "p1"


async def test_get_channel_detail_404_when_missing(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/channels/999999")
    assert resp.status_code == 404
