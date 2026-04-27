"""Tests for channel + source mutations on /api/channels."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Channel, ChannelSource
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession], monkeypatch):
    from app.webapi.deps import get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    # Mutation handlers reach for `create_session_maker()` to open their own
    # session for the repo calls — point it at the in-memory test maker.
    from app.webapi.routes import channels as channels_route

    monkeypatch.setattr(channels_route, "create_session_maker", lambda: db_session_maker)

    app.dependency_overrides[get_session] = _override_session
    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)


async def _seed_channel(session: AsyncSession, *, telegram_id: int = -100300) -> int:
    ch = Channel(name="seed", language="en", telegram_id=telegram_id)
    session.add(ch)
    await session.commit()
    await session.refresh(ch)
    return ch.id


async def test_create_channel_returns_detail(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.post(
            "/api/channels",
            json={"telegram_id": -100400, "name": "new", "language": "en", "description": "d"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "new"
    assert body["telegram_id"] == -100400
    assert body["sources"] == []
    assert body["recent_posts"] == []


async def test_create_channel_409_on_duplicate_telegram_id(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        await _seed_channel(s, telegram_id=-100401)

    async with client_factory() as client:
        resp = await client.post("/api/channels", json={"telegram_id": -100401, "name": "dup"})
    assert resp.status_code == 409


async def test_update_channel_changes_fields(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        channel_id = await _seed_channel(s)

    async with client_factory() as client:
        resp = await client.patch(
            f"/api/channels/{channel_id}",
            json={"name": "renamed", "max_posts_per_day": 7, "enabled": False},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "renamed"
    assert body["max_posts_per_day"] == 7
    assert body["enabled"] is False


async def test_update_channel_404(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.patch("/api/channels/9999", json={"name": "x"})
    assert resp.status_code == 404


async def test_delete_channel(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        channel_id = await _seed_channel(s)

    async with client_factory() as client:
        resp = await client.delete(f"/api/channels/{channel_id}")
    assert resp.status_code == 200, resp.text

    async with db_session_maker() as s:
        gone = (await s.execute(select(Channel).where(Channel.id == channel_id))).scalar_one_or_none()
        assert gone is None


async def test_add_source_creates_row(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        channel_id = await _seed_channel(s)

    async with client_factory() as client:
        resp = await client.post(
            f"/api/channels/{channel_id}/sources",
            json={"url": "https://example.com/feed.xml", "title": "Example"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["url"] == "https://example.com/feed.xml"
    assert body["enabled"] is True


async def test_add_source_409_on_duplicate(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        channel_id = await _seed_channel(s)
        ch = (await s.execute(select(Channel).where(Channel.id == channel_id))).scalar_one()
        s.add(ChannelSource(channel_id=ch.telegram_id, url="https://dup.example/feed"))
        await s.commit()

    async with client_factory() as client:
        resp = await client.post(
            f"/api/channels/{channel_id}/sources",
            json={"url": "https://dup.example/feed"},
        )
    assert resp.status_code == 409


async def test_toggle_source_enabled(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        channel_id = await _seed_channel(s)
        ch = (await s.execute(select(Channel).where(Channel.id == channel_id))).scalar_one()
        src = ChannelSource(channel_id=ch.telegram_id, url="https://x.example/feed")
        s.add(src)
        await s.commit()
        source_id = src.id

    async with client_factory() as client:
        resp = await client.patch(
            f"/api/channels/{channel_id}/sources/{source_id}",
            json={"enabled": False},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False


async def test_delete_source(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        channel_id = await _seed_channel(s)
        ch = (await s.execute(select(Channel).where(Channel.id == channel_id))).scalar_one()
        src = ChannelSource(channel_id=ch.telegram_id, url="https://y.example/feed")
        s.add(src)
        await s.commit()
        source_id = src.id

    async with client_factory() as client:
        resp = await client.delete(f"/api/channels/{channel_id}/sources/{source_id}")
    assert resp.status_code == 200, resp.text

    async with db_session_maker() as s:
        gone = (await s.execute(select(ChannelSource).where(ChannelSource.id == source_id))).scalar_one_or_none()
        assert gone is None
