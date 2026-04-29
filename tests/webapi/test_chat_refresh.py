"""Tests for POST /api/chats/{id}/refresh and GET /api/chats/{id}/avatar.

The refresh endpoint exercises ``fetch_chat_photo_file_id`` (Bot API
``getChat``) and the optional Telethon title sync. The avatar endpoint
proxies bytes via ``Bot.download``. Both rely on a publish_bot override.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import settings
from app.db.models import Chat
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


def _bot_with_photo(file_id: str) -> MagicMock:
    """Bot mock whose get_chat returns a chat with a photo of file_id."""
    bot = MagicMock()
    bot.get_chat = AsyncMock(return_value=MagicMock(photo=MagicMock(big_file_id=file_id, small_file_id="small")))
    bot.download = AsyncMock(return_value=io.BytesIO(b"\xff\xd8\xff\xe0jpegbytes"))
    return bot


def _bot_without_photo() -> MagicMock:
    bot = MagicMock()
    bot.get_chat = AsyncMock(return_value=MagicMock(photo=None))
    bot.download = AsyncMock(return_value=None)
    return bot


@pytest.fixture
def client_factory(db_session_maker):
    from app.webapi.deps import get_publish_bot, get_session, get_telethon

    bot_holder: dict[str, MagicMock] = {"bot": _bot_with_photo("photo-file-id-1")}
    telethon_holder: dict[str, object] = {"telethon": None}

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    async def _override_publish_bot():
        return bot_holder["bot"]

    async def _override_telethon():
        return telethon_holder["telethon"]

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_publish_bot] = _override_publish_bot
    app.dependency_overrides[get_telethon] = _override_telethon
    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make, bot_holder, telethon_holder
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_publish_bot, None)
    app.dependency_overrides.pop(get_telethon, None)


async def test_refresh_caches_photo_file_id(client_factory, db_session_maker) -> None:
    make, _bot_holder, _telethon_holder = client_factory
    async with db_session_maker() as s:
        s.add(Chat(id=-7001, title="A"))
        await s.commit()

    async with make() as client:
        resp = await client.post("/api/chats/-7001/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_photo"] is True
    assert body["last_synced_at"] is not None

    async with db_session_maker() as s:
        chat = (await s.execute(select(Chat).where(Chat.id == -7001))).scalar_one()
    assert chat.photo_file_id == "photo-file-id-1"
    assert chat.last_synced_at is not None


async def test_refresh_clears_photo_when_chat_has_none(client_factory, db_session_maker) -> None:
    """Chat had a cached photo, then was un-set upstream — refresh keeps the
    old cache (we only overwrite on positive responses; we don't actively
    null-out, since a transient API hiccup shouldn't blow away the icon)."""
    make, bot_holder, _telethon_holder = client_factory
    bot_holder["bot"] = _bot_without_photo()
    async with db_session_maker() as s:
        chat = Chat(id=-7002, title="B")
        chat.photo_file_id = "stale-cached-id"
        s.add(chat)
        await s.commit()

    async with make() as client:
        resp = await client.post("/api/chats/-7002/refresh")

    assert resp.status_code == 200
    async with db_session_maker() as s:
        chat = (await s.execute(select(Chat).where(Chat.id == -7002))).scalar_one()
    assert chat.photo_file_id == "stale-cached-id"


async def test_refresh_syncs_title_via_telethon(client_factory, db_session_maker) -> None:
    make, _bot_holder, telethon_holder = client_factory
    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(title="Renamed Live", member_count=42))
    telethon_holder["telethon"] = tc

    async with db_session_maker() as s:
        s.add(Chat(id=-7003, title="Old DB Title"))
        await s.commit()

    async with make() as client:
        resp = await client.post("/api/chats/-7003/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Renamed Live"


async def test_refresh_returns_404_for_unknown_chat(client_factory) -> None:
    make, _bot_holder, _telethon_holder = client_factory
    async with make() as client:
        resp = await client.post("/api/chats/-9999/refresh")
    assert resp.status_code == 404


async def test_avatar_proxies_bytes(client_factory, db_session_maker) -> None:
    make, _bot_holder, _telethon_holder = client_factory
    async with db_session_maker() as s:
        chat = Chat(id=-7004, title="C")
        chat.photo_file_id = "photo-file-id-1"
        s.add(chat)
        await s.commit()

    async with make() as client:
        resp = await client.get("/api/chats/-7004/avatar")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=3600"
    assert resp.content.startswith(b"\xff\xd8\xff\xe0")  # JPEG SOI marker


async def test_avatar_returns_404_when_no_cache(client_factory, db_session_maker) -> None:
    make, _bot_holder, _telethon_holder = client_factory
    async with db_session_maker() as s:
        s.add(Chat(id=-7005, title="D"))
        await s.commit()

    async with make() as client:
        resp = await client.get("/api/chats/-7005/avatar")

    assert resp.status_code == 404
