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


async def test_update_chat_missing_parent_422(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-2005, title="x"))
        await s.commit()
    async with client_factory() as client:
        resp = await client.patch("/api/chats/-2005", json={"parent_chat_id": -9999})
    assert resp.status_code == 422


async def test_update_chat_parent_cycle_422(client_factory, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-2006, title="root"))
        s.add(Chat(id=-2007, title="child", parent_chat_id=-2006))
        await s.commit()
    async with client_factory() as client:
        resp = await client.patch("/api/chats/-2006", json={"parent_chat_id": -2007})
    assert resp.status_code == 422


class TestPublishingAChat:
    """Setting the public link is what puts a chat on the public page.

    It is the only field on this endpoint whose value is rendered to strangers
    rather than shown back to the admin who typed it, so it is the only one with
    a shape.
    """

    async def test_a_telegram_link_publishes(self, client_factory, db_session_maker) -> None:
        async with db_session_maker() as s:
            s.add(Chat(id=-2101, title="ČVUT FIT"))
            await s.commit()

        async with client_factory() as client:
            resp = await client.patch("/api/chats/-2101", json={"public_link": "https://t.me/cvut_fit"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["public_link"] == "https://t.me/cvut_fit"

    @pytest.mark.parametrize(
        "link",
        [
            "https://t.me/+AAAAAAAAAAAAAAAA",
            "https://t.me/joinchat/AAAAAAAAAAAAAAAA",
        ],
    )
    async def test_an_invite_link_publishes(self, client_factory, db_session_maker, link: str) -> None:
        """Closed chats have no username, so an invite hash is the only way in."""
        async with db_session_maker() as s:
            s.add(Chat(id=-2102, title="closed"))
            await s.commit()

        async with client_factory() as client:
            resp = await client.patch("/api/chats/-2102", json={"public_link": link})

        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize(
        "link",
        [
            "javascript:alert(1)",
            "http://t.me/cvut_fit",
            "https://evil.example/t.me/cvut_fit",
            "https://t.me.evil.example/cvut_fit",
            "не ссылка",
        ],
    )
    async def test_anything_that_is_not_a_chat_link_is_refused(
        self, client_factory, db_session_maker, link: str
    ) -> None:
        """This value ends up in an href on a page anybody can open."""
        async with db_session_maker() as s:
            s.add(Chat(id=-2103, title="x"))
            await s.commit()

        async with client_factory() as client:
            resp = await client.patch("/api/chats/-2103", json={"public_link": link})

        assert resp.status_code == 422
        async with db_session_maker() as s:
            ch = (await s.execute(select(Chat).where(Chat.id == -2103))).scalar_one()
            assert ch.public_link is None

    async def test_clearing_the_field_takes_the_chat_down(self, client_factory, db_session_maker) -> None:
        """A form sends an empty string for a cleared input, and it must mean
        "take it down" — not "publish with a link that goes nowhere"."""
        async with db_session_maker() as s:
            s.add(Chat(id=-2104, title="listed", public_link="https://t.me/listed_chat"))
            await s.commit()

        async with client_factory() as client:
            resp = await client.patch("/api/chats/-2104", json={"public_link": "   "})

        assert resp.status_code == 200, resp.text
        assert resp.json()["public_link"] is None
        async with db_session_maker() as s:
            ch = (await s.execute(select(Chat).where(Chat.id == -2104))).scalar_one()
            assert ch.public_link is None

    async def test_a_patch_that_says_nothing_about_it_leaves_it_alone(self, client_factory, db_session_maker) -> None:
        """Renaming a chat must not quietly unpublish it."""
        async with db_session_maker() as s:
            s.add(Chat(id=-2105, title="listed", public_link="https://t.me/listed_chat"))
            await s.commit()

        async with client_factory() as client:
            resp = await client.patch("/api/chats/-2105", json={"title": "renamed"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["public_link"] == "https://t.me/listed_chat"


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
