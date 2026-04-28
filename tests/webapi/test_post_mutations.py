"""Tests for /api/posts/{id}/{approve,reject,text} mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from app.core.config import settings
from app.core.enums import PostStatus
from app.db.models import Channel, ChannelPost
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession], monkeypatch):
    """Wire test session maker, stub publish_bot, dev-bypass auth."""
    from app.webapi.deps import get_publish_bot, get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    fake_bot = AsyncMock()

    async def _override_publish_bot():
        return fake_bot

    # The route + service layer reach for `create_session_maker()` directly to
    # open their own sessions for `with_for_update`. Patch the symbol they
    # imported so they get the test SQLite maker instead of a fresh PG one.
    from app.webapi.routes import posts as posts_route

    monkeypatch.setattr(posts_route, "create_session_maker", lambda: db_session_maker)

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


async def _seed_post(session: AsyncSession, *, status: PostStatus = PostStatus.DRAFT) -> int:
    ch = Channel(name="x", language="en", telegram_id=-100200)
    session.add(ch)
    await session.flush()
    post = ChannelPost(
        channel_id=ch.telegram_id,
        external_id="z" * 16,
        title="t",
        post_text="hello",
        status=status,
    )
    session.add(post)
    await session.commit()
    return post.id


async def test_edit_text_updates_post(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        post_id = await _seed_post(s)

    async with make() as client:
        resp = await client.patch(f"/api/posts/{post_id}/text", json={"text": "rewritten"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["post_id"] == post_id
    assert "updated" in body["message"].lower()

    async with db_session_maker() as s:
        post = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert post.post_text == "rewritten"


async def test_reject_marks_rejected(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        post_id = await _seed_post(s)

    async with make() as client:
        resp = await client.post(f"/api/posts/{post_id}/reject")
    assert resp.status_code == 200, resp.text

    async with db_session_maker() as s:
        post = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert post.status == PostStatus.REJECTED


async def test_approve_calls_publisher(client_factory, db_session_maker, monkeypatch) -> None:
    make, _bot = client_factory
    # Stub the publisher used inside the route (avoids real Telegram call).
    from app.webapi.routes import posts as posts_route

    async def _fake_publish(*args, **kwargs):
        return 12345

    monkeypatch.setattr(posts_route, "_publish_to_channel", _fake_publish)

    async with db_session_maker() as s:
        post_id = await _seed_post(s)

    async with make() as client:
        resp = await client.post(f"/api/posts/{post_id}/approve")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["published_msg_id"] == 12345


async def test_404_when_missing(client_factory) -> None:
    make, _bot = client_factory
    async with make() as client:
        resp = await client.patch("/api/posts/99999/text", json={"text": "x"})
    assert resp.status_code == 404


async def test_regenerate_404_when_missing(client_factory) -> None:
    make, _bot = client_factory
    async with make() as client:
        resp = await client.post("/api/posts/99999/regenerate")
    assert resp.status_code == 404


async def test_regenerate_refuses_already_published(client_factory, db_session_maker) -> None:
    """Status check happens inside regen_post_text — route returns 200 with the
    refusal message instead of mutating the post."""
    make, _bot = client_factory
    async with db_session_maker() as s:
        post_id = await _seed_post(s, status=PostStatus.APPROVED)

    async with make() as client:
        resp = await client.post(f"/api/posts/{post_id}/regenerate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "already published" in body["message"].lower()
    async with db_session_maker() as s:
        post = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert post.status == PostStatus.APPROVED  # untouched


async def test_image_remove_404_when_post_missing(client_factory) -> None:
    make, _bot = client_factory
    async with make() as client:
        resp = await client.delete("/api/posts/99999/images/0")
    assert resp.status_code == 404


async def test_image_clear_drops_selected_keeps_pool(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        ch = Channel(name="x", language="en", telegram_id=-100200)
        s.add(ch)
        await s.flush()
        post = ChannelPost(
            channel_id=ch.telegram_id,
            external_id="z" * 16,
            title="t",
            post_text="hello",
            image_urls=["https://a.example/img1.jpg", "https://a.example/img2.jpg"],
            image_candidates=[
                {"url": "https://a.example/img1.jpg", "source": "rss", "selected": True},
                {"url": "https://a.example/img2.jpg", "source": "rss", "selected": True},
                {"url": "https://a.example/img3.jpg", "source": "rss", "selected": False},
            ],
        )
        s.add(post)
        await s.commit()
        post_id = post.id

    async with make() as client:
        resp = await client.delete(f"/api/posts/{post_id}/images")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["image_urls"] == []
    assert len(body["image_candidates"]) == 3
    assert all(not c["selected"] for c in body["image_candidates"])


async def test_image_reorder_validates_permutation(client_factory, db_session_maker) -> None:
    make, _bot = client_factory
    async with db_session_maker() as s:
        ch = Channel(name="x", language="en", telegram_id=-100200)
        s.add(ch)
        await s.flush()
        post = ChannelPost(
            channel_id=ch.telegram_id,
            external_id="z" * 16,
            title="t",
            post_text="hello",
            image_urls=["https://a.example/1", "https://a.example/2", "https://a.example/3"],
        )
        s.add(post)
        await s.commit()
        post_id = post.id

    async with make() as client:
        good = await client.post(f"/api/posts/{post_id}/images/reorder", json={"order": [2, 0, 1]})
        bad = await client.post(f"/api/posts/{post_id}/images/reorder", json={"order": [0, 0, 1]})
    assert good.status_code == 200
    assert good.json()["image_urls"] == [
        "https://a.example/3",
        "https://a.example/1",
        "https://a.example/2",
    ]
    assert bad.status_code == 200  # service-level rejection, not HTTP
    assert "invalid" in bad.json()["message"].lower()
