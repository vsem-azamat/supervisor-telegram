"""Tests for /api/stats endpoints."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.channel import cost_tracker
from app.core.config import settings
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import Channel, ChannelPost
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
        return None  # no telethon in tests

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_telethon] = _override_get_telethon
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_telethon, None)


@pytest.fixture(autouse=True)
def _clean_cost_history():
    cost_tracker.reset_usage_history()
    yield
    cost_tracker.reset_usage_history()


async def test_home_stats_shape(client_factory, db_session_maker) -> None:
    async with db_session_maker() as session:
        session.add(Channel(telegram_id=-1001, name="A", username="a"))
        session.add(
            ChannelPost(
                channel_id=-1001,
                external_id="e-draft",
                title="draft post",
                post_text="x",
                status=PostStatus.DRAFT,
            )
        )
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    assert resp.status_code == 200
    body = resp.json()
    assert "drafts" in body
    assert "scheduled_next_24h" in body
    assert "session_cost" in body
    assert any(d["channel_id"] == -1001 and d["count"] >= 1 for d in body["drafts"])


async def test_home_stats_scheduled_window_is_24h(client_factory, db_session_maker) -> None:
    now = utc_now()
    far_future = now + datetime.timedelta(days=3)
    soon = now + datetime.timedelta(hours=6)

    async with db_session_maker() as session:
        session.add(Channel(telegram_id=-1002, name="B", username="b"))
        post_far = ChannelPost(
            channel_id=-1002,
            external_id="far",
            title="far",
            post_text="x",
            status=PostStatus.SCHEDULED,
        )
        post_far.scheduled_at = far_future
        post_soon = ChannelPost(
            channel_id=-1002,
            external_id="soon",
            title="soon",
            post_text="x",
            status=PostStatus.SCHEDULED,
        )
        post_soon.scheduled_at = soon
        session.add(post_far)
        session.add(post_soon)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    titles = [e["title"] for e in resp.json()["scheduled_next_24h"]]
    assert "soon" in titles
    assert "far" not in titles


async def test_home_includes_post_views(client_factory, db_session_maker) -> None:
    import datetime

    from app.core.enums import PostStatus
    from app.db.models import Channel, ChannelPost

    async with db_session_maker() as session:
        session.add(Channel(telegram_id=-2001, name="V", username="v"))
        post = ChannelPost(channel_id=-2001, external_id="e1", title="P1", post_text="x")
        post.status = PostStatus.APPROVED
        post.telegram_message_id = 42
        post.published_at = datetime.datetime(2026, 4, 21, 10, 0, 0)
        session.add(post)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    assert "post_views" in body
    pvs = body["post_views"]
    assert len(pvs) == 1
    assert pvs[0]["post_id"] > 0
    assert pvs[0]["title"] == "P1"
    assert pvs[0]["views"] == 0  # telethon stubbed to None in tests


async def test_home_includes_chat_heatmap_totals(client_factory, db_session_maker) -> None:
    import datetime

    from app.db.models import Chat, Message

    async with db_session_maker() as session:
        session.add(Chat(id=-3001, title="H"))
        for i in range(5):
            m = Message(chat_id=-3001, user_id=1, message_id=i)
            m.timestamp = datetime.datetime(2026, 4, 21, 12, 0, 0)
            session.add(m)
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    assert body["chat_heatmap"][0]["chat_id"] == -3001
    assert body["chat_heatmap"][0]["total_messages"] == 5


async def test_home_members_delta_computes_24h_baseline(client_factory, db_session_maker) -> None:
    import datetime

    from app.core.time import utc_now
    from app.db.models import Chat, ChatMemberSnapshot

    now = utc_now()
    async with db_session_maker() as session:
        session.add(Chat(id=-4001, title="M"))
        session.add(
            ChatMemberSnapshot(
                chat_id=-4001,
                member_count=100,
                captured_at=now - datetime.timedelta(hours=25),
            )
        )
        session.add(
            ChatMemberSnapshot(
                chat_id=-4001,
                member_count=110,
                captured_at=now - datetime.timedelta(minutes=5),
            )
        )
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    delta = next(d for d in body["members_delta"] if d["chat_id"] == -4001)
    assert delta["current"] == 110
    assert delta["delta_24h"] == 10
    assert delta["delta_7d"] is None  # no baseline ≥7d old yet


async def test_home_members_delta_includes_chat_with_only_stale_snapshots(client_factory, db_session_maker) -> None:
    """Chats with snapshots older than 7d (but within 30d lookback) must
    still appear in members_delta with their stale count and None deltas."""
    import datetime

    from app.core.time import utc_now
    from app.db.models import Chat, ChatMemberSnapshot

    now = utc_now()
    async with db_session_maker() as session:
        session.add(Chat(id=-4002, title="Stale"))
        # Single snapshot from 10 days ago — only data point for this chat.
        session.add(
            ChatMemberSnapshot(
                chat_id=-4002,
                member_count=200,
                captured_at=now - datetime.timedelta(days=10),
            )
        )
        await session.commit()

    async with client_factory() as client:
        resp = await client.get("/api/stats/home")

    body = resp.json()
    delta = next((d for d in body["members_delta"] if d["chat_id"] == -4002), None)
    assert delta is not None, "Chat with only stale snapshots must appear in members_delta"
    assert delta["current"] == 200  # the single stale snapshot is still the current
    # Only one data point — no older baseline exists for either window.
    assert delta["delta_24h"] is None
    assert delta["delta_7d"] is None
