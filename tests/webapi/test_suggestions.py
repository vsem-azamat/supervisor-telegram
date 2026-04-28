"""Tests for /api/suggestions — mechanical setup-gap detection."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.core.time import utc_now
from app.db.models import Channel, ChannelSource, Chat, Message
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client(db_session_maker: async_sessionmaker[AsyncSession]):
    """Wire test session to the FastAPI dep + dev-bypass auth.

    Returns a factory so tests that hit the endpoint twice (orphan rule
    needs to verify it fires only after the second chat lands) get a
    fresh AsyncClient each call — httpx clients can't be reopened."""
    from app.webapi.deps import get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)


def _kinds(body: dict) -> list[str]:
    return [item["kind"] for item in body["items"]]


async def test_empty_db_returns_no_items(client) -> None:
    async with client() as c:
        resp = await c.get("/api/suggestions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert "generated_at" in body


async def test_disabled_channel_surfaces(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Channel(telegram_id=-100100, name="Off Air", enabled=False))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "disabled_channel" in _kinds(body)
    item = next(i for i in body["items"] if i["kind"] == "disabled_channel")
    assert item["target_label"] == "Off Air"
    assert item["action_url"].startswith("/channels/")


async def test_channel_without_sources_surfaces(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Channel(telegram_id=-100200, name="Empty", enabled=True))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "channel_without_sources" in _kinds(body)


async def test_channel_with_sources_does_not_surface(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        ch = Channel(telegram_id=-100300, name="Stocked", enabled=True)
        s.add(ch)
        await s.flush()
        s.add(ChannelSource(channel_id=ch.id, url="https://example.com/feed", source_type="rss"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "channel_without_sources" not in _kinds(body)


async def test_channel_without_username_surfaces(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Channel(telegram_id=-100400, name="No Handle", enabled=True, username=None))
        # plus a control: enabled with username should not flag
        s.add(Channel(telegram_id=-100401, name="Has Handle", enabled=True, username="public"))
        await s.flush()
        # Add a source for both so the no-sources rule doesn't trigger.
        from sqlalchemy import select

        for ch in (await s.execute(select(Channel))).scalars():
            s.add(ChannelSource(channel_id=ch.id, url=f"https://example.com/{ch.id}", source_type="rss"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    items = [i for i in body["items"] if i["kind"] == "channel_without_username"]
    assert len(items) == 1
    assert items[0]["target_label"] == "No Handle"


async def test_unmoderated_chat_surfaces_only_after_grace(client, db_session_maker) -> None:
    """Both is_welcome_enabled and is_captcha_enabled false AND modified_at older
    than the grace window — only then does the rule trigger."""
    old = utc_now() - datetime.timedelta(days=30)
    async with db_session_maker() as s:
        # Stale unmoderated — should flag
        stale = Chat(id=-1, title="Stale Group", is_welcome_enabled=False, is_captcha_enabled=False)
        stale.created_at = old
        stale.modified_at = old
        s.add(stale)
        # Recently added unmoderated — within grace, should NOT flag
        fresh = Chat(id=-2, title="Fresh Group", is_welcome_enabled=False, is_captcha_enabled=False)
        s.add(fresh)
        # Stale but moderated — should NOT flag
        guarded = Chat(id=-3, title="Guarded", is_welcome_enabled=True, is_captcha_enabled=False)
        guarded.created_at = old
        guarded.modified_at = old
        s.add(guarded)
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    items = [i for i in body["items"] if i["kind"] == "unmoderated_chat"]
    labels = {i["target_label"] for i in items}
    assert "Stale Group" in labels
    assert "Fresh Group" not in labels
    assert "Guarded" not in labels


async def test_silent_chat_surfaces_when_no_recent_messages(client, db_session_maker) -> None:
    old = utc_now() - datetime.timedelta(days=30)
    async with db_session_maker() as s:
        silent = Chat(id=-10, title="Silent Group")
        silent.created_at = old
        silent.modified_at = old
        s.add(silent)
        active = Chat(id=-11, title="Active Group")
        active.created_at = old
        active.modified_at = old
        s.add(active)
        await s.flush()
        s.add(Message(chat_id=active.id, user_id=1, message_id=1, message="hi"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    items = [i for i in body["items"] if i["kind"] == "silent_chat"]
    labels = {i["target_label"] for i in items}
    assert "Silent Group" in labels
    assert "Active Group" not in labels


async def test_orphan_chats_require_at_least_two(client, db_session_maker) -> None:
    """A single isolated chat is fine — the rule needs >=2 to fire."""
    async with db_session_maker() as s:
        s.add(Chat(id=-20, title="Solo"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "orphan_chat" not in _kinds(body)

    async with db_session_maker() as s:
        s.add(Chat(id=-21, title="Also Solo"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    items = [i for i in body["items"] if i["kind"] == "orphan_chat"]
    assert len(items) == 2


async def test_orphan_excludes_chats_with_relations(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        root = Chat(id=-30, title="Root")
        child = Chat(id=-31, title="Child", parent_chat_id=-30)
        s.add(root)
        s.add(child)
        # And one truly isolated, just to keep the rule's >=2 check from failing
        # for orphan_chat — but since "Root" has a child it's not orphan, and
        # "Child" has a parent, only the standalone is orphan, which is <2 → no fire.
        s.add(Chat(id=-32, title="Loner"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "orphan_chat" not in _kinds(body)


async def test_network_without_channel_surfaces(client, db_session_maker) -> None:
    """Tree with >=2 chats but no Channel.review_chat_id pointing inside → fire."""
    async with db_session_maker() as s:
        s.add(Channel(telegram_id=-100500, name="Lonely", enabled=True, username="lonely"))
        s.add(ChannelSource(channel_id=1, url="https://x", source_type="rss"))  # avoid no-sources noise
        s.add(Chat(id=-40, title="Faculty Root"))
        s.add(Chat(id=-41, title="Faculty Sub", parent_chat_id=-40))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    items = [i for i in body["items"] if i["kind"] == "network_without_channel"]
    assert len(items) == 1
    assert items[0]["target_label"] == "Faculty Root"


async def test_network_with_channel_does_not_surface(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-50, title="Wired Root"))
        s.add(Chat(id=-51, title="Wired Sub", parent_chat_id=-50))
        s.add(
            Channel(
                telegram_id=-100600,
                name="Wired",
                enabled=True,
                username="wired",
                review_chat_id=-50,
            )
        )
        s.add(ChannelSource(channel_id=1, url="https://x", source_type="rss"))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "network_without_channel" not in _kinds(body)


async def test_network_rule_skips_when_no_channels_exist(client, db_session_maker) -> None:
    async with db_session_maker() as s:
        s.add(Chat(id=-60, title="Greenfield Root"))
        s.add(Chat(id=-61, title="Greenfield Sub", parent_chat_id=-60))
        await s.commit()

    async with client() as c:
        resp = await c.get("/api/suggestions")
    body = resp.json()
    assert "network_without_channel" not in _kinds(body)
