"""Tests for intentionally unauthenticated public API projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Channel, ChatLink
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
    orig_admins = list(settings.admin.super_admins)
    settings.admin.super_admins = [1]
    from app.webapi.deps import require_super_admin

    app.dependency_overrides.pop(require_super_admin, None)
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    settings.admin.super_admins = orig_admins


async def test_public_catalog_is_readable_without_session(client_factory, db_session_maker) -> None:
    async with db_session_maker() as session:
        session.add(ChatLink(text="Public Chat", link="t.me/public_chat"))
        session.add(Channel(telegram_id=-2001, name="Enabled Channel", username="enabled", enabled=True))
        session.add(Channel(telegram_id=-2002, name="Disabled Channel", username="disabled", enabled=False))
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/public/catalog")

    assert resp.status_code == 200
    assert resp.json() == [
        {"resource_type": "channel", "id": 1, "title": "Enabled Channel", "subtitle": "@enabled"},
        {"resource_type": "chat", "id": 1, "title": "Public Chat", "subtitle": "t.me/public_chat"},
    ]


async def test_public_catalog_does_not_open_admin_routes(client_factory) -> None:
    async with client_factory() as client:
        catalog = await client.get("/api/public/catalog")
        me = await client.get("/api/auth/me")
        admin_channels = await client.get("/api/channels")

    assert catalog.status_code == 200
    assert me.status_code == 401
    assert admin_channels.status_code == 401
