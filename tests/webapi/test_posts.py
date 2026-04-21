"""Tests for /api/posts endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    """Yield an httpx client with the webapi DB dep overridden to use the
    test session_maker."""
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


async def _seed_post(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    channel_id: int = -1001,
    status: str = PostStatus.DRAFT,
    title: str = "t",
) -> int:
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=channel_id,
            external_id="ext-1",
            title=title,
            post_text="body",
            status=status,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


async def test_list_posts_filters_by_channel(
    client_factory,
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """channel_id query param narrows results to that channel only."""
    await _seed_post(db_session_maker, channel_id=-1001, title="a")
    await _seed_post(db_session_maker, channel_id=-1002, title="b")

    async with client_factory() as client:
        resp = await client.get("/api/posts", params={"channel_id": -1002})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["channel_id"] == -1002


async def test_get_post_detail_returns_full_shape(
    client_factory,
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """/api/posts/{id} returns PostDetail with external_id field present."""
    post_id = await _seed_post(db_session_maker, title="t42")

    async with client_factory() as client:
        resp = await client.get(f"/api/posts/{post_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == post_id
    assert body["title"] == "t42"
    assert "external_id" in body


async def test_get_post_detail_returns_404_when_missing(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/posts/999999")
    assert resp.status_code == 404
