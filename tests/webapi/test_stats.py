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
