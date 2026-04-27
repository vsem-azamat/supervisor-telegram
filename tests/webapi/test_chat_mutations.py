"""Tests for PATCH /api/chats/{id} — per-chat moderation toggles."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.db.models import Chat
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session, get_telethon

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    async def _override_telethon():
        return None

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_telethon] = _override_telethon
    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_telethon, None)


async def test_update_chat_toggles(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-2001, title="moderated"))
        await s.commit()

    async with client_factory() as client:
        resp = await client.patch(
            "/api/chats/-2001",
            json={
                "title": "renamed",
                "is_welcome_enabled": True,
                "is_captcha_enabled": True,
                "welcome_message": "hi",
                "time_delete": 120,
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "renamed"
    assert body["is_welcome_enabled"] is True
    assert body["is_captcha_enabled"] is True

    async with db_session_maker() as s:
        ch = (await s.execute(select(Chat).where(Chat.id == -2001))).scalar_one()
        assert ch.welcome_message == "hi"
        assert ch.time_delete == 120


async def test_update_chat_404(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.patch("/api/chats/99999", json={"title": "x"})
    assert resp.status_code == 404


async def test_update_chat_negative_time_delete_422(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-2002, title="x"))
        await s.commit()
    async with client_factory() as client:
        resp = await client.patch("/api/chats/-2002", json={"time_delete": -5})
    assert resp.status_code == 422


async def test_update_chat_self_parent_422(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-2003, title="x"))
        await s.commit()
    async with client_factory() as client:
        resp = await client.patch("/api/chats/-2003", json={"parent_chat_id": -2003})
    assert resp.status_code == 422


async def test_update_chat_partial_keeps_other_fields(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-2004, title="orig", welcome_message="orig-welcome"))
        await s.commit()

    async with client_factory() as client:
        resp = await client.patch("/api/chats/-2004", json={"is_welcome_enabled": True})
    assert resp.status_code == 200, resp.text

    async with db_session_maker() as s:
        ch = (await s.execute(select(Chat).where(Chat.id == -2004))).scalar_one()
        assert ch.welcome_message == "orig-welcome"
        assert ch.title == "orig"
        assert ch.is_welcome_enabled is True
