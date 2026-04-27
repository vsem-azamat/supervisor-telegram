"""Tests for /api/users/{id}/block — global ban/unban via blacklist service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from app.core.config import settings
from app.db.models import User
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_publish_bot, get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    fake_bot = AsyncMock()

    async def _override_publish_bot():
        return fake_bot

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_publish_bot] = _override_publish_bot
    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make, fake_bot
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_publish_bot, None)


async def test_block_marks_user_blocked(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        s.add(User(id=42, username="alice"))
        await s.commit()

    async with make() as client:
        resp = await client.post("/api/users/42/block", json={"revoke_messages": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["blocked"] is True

    async with db_session_maker() as s:
        u = (await s.execute(select(User).where(User.id == 42))).scalar_one()
        assert u.blocked is True


async def test_block_creates_user_when_unknown(client_factory, db_session_maker) -> None:
    """Unknown user_id (never seen before) should still produce a User row in
    blacklisted state — same semantics as the bot's /ban command."""
    make, _bot = client_factory
    async with make() as client:
        resp = await client.post("/api/users/99/block", json={})
    assert resp.status_code == 200, resp.text

    async with db_session_maker() as s:
        u = (await s.execute(select(User).where(User.id == 99))).scalar_one()
        assert u.blocked is True


async def test_unblock_clears_flag(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        s.add(User(id=43, username="bob", blocked=True))
        await s.commit()

    async with make() as client:
        resp = await client.delete("/api/users/43/block")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["blocked"] is False

    async with db_session_maker() as s:
        u = (await s.execute(select(User).where(User.id == 43))).scalar_one()
        assert u.blocked is False


async def test_unblock_404_when_user_unknown(client_factory) -> None:
    make, _bot = client_factory
    async with make() as client:
        resp = await client.delete("/api/users/99999/block")
    assert resp.status_code == 404


async def test_get_status_returns_blocked_flag(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        s.add(User(id=44, username="carol", blocked=True))
        await s.commit()

    async with make() as client:
        resp = await client.get("/api/users/44")
    assert resp.status_code == 200
    assert resp.json()["blocked"] is True


async def test_get_status_404_when_unknown(client_factory) -> None:
    make, _bot = client_factory
    async with make() as client:
        resp = await client.get("/api/users/99999")
    assert resp.status_code == 404
