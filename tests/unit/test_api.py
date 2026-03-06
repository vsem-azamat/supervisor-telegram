"""Tests for magic link auth, stats queries, and API routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import ChannelPost, ChannelSource
from app.presentation.api.auth import (
    _tokens,
    clear_tokens,
    generate_magic_link,
    validate_token,
)
from app.presentation.api.routes import create_api_app
from app.presentation.api.stats import get_all_channels_stats, get_channel_stats, get_recent_posts, get_sources
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# -------------------------------------------------------------------------
# Auth unit tests
# -------------------------------------------------------------------------


class TestMagicLinkAuth:
    """Tests for generate_magic_link / validate_token."""

    def setup_method(self) -> None:
        clear_tokens()

    def teardown_method(self) -> None:
        clear_tokens()

    def test_generate_returns_string(self) -> None:
        token = generate_magic_link("a@example.com")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_validate_returns_user_info(self) -> None:
        token = generate_magic_link("a@example.com", role="admin")
        info = validate_token(token)
        assert info is not None
        assert info["email"] == "a@example.com"
        assert info["role"] == "admin"

    def test_validate_invalid_token(self) -> None:
        assert validate_token("nonexistent-token") is None

    def test_token_expiry(self) -> None:
        token = generate_magic_link("b@example.com")
        # Manually expire the token
        _tokens[token]["expires_at"] = datetime.now(tz=UTC) - timedelta(hours=1)
        assert validate_token(token) is None
        # Token should be cleaned up
        assert token not in _tokens

    def test_default_role_is_viewer(self) -> None:
        token = generate_magic_link("c@example.com")
        info = validate_token(token)
        assert info is not None
        assert info["role"] == "viewer"

    def test_multiple_tokens_independent(self) -> None:
        t1 = generate_magic_link("x@example.com", role="admin")
        t2 = generate_magic_link("y@example.com", role="viewer")
        assert t1 != t2
        info1 = validate_token(t1)
        info2 = validate_token(t2)
        assert info1 is not None
        assert info2 is not None
        assert info1["email"] == "x@example.com"
        assert info2["email"] == "y@example.com"


# -------------------------------------------------------------------------
# Stats query tests (SQLite in-memory)
# -------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def stats_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def stats_session_maker(stats_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=stats_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture()
async def seeded_session_maker(
    stats_session_maker: async_sessionmaker[AsyncSession],
) -> async_sessionmaker[AsyncSession]:
    """Seed DB with sample channel data."""
    async with stats_session_maker() as session:
        # Sources
        session.add(ChannelSource(channel_id="ch1", url="https://feed1.com/rss", title="Feed 1"))
        session.add(ChannelSource(channel_id="ch1", url="https://feed2.com/rss", title="Feed 2"))
        s3 = ChannelSource(channel_id="ch1", url="https://feed3.com/rss", title="Feed 3 (disabled)")
        s3.enabled = False
        s3.relevance_score = 0.2
        session.add(s3)

        # Posts
        session.add(
            ChannelPost(channel_id="ch1", external_id="e1", title="Post 1", post_text="text1", status="approved")
        )
        session.add(
            ChannelPost(channel_id="ch1", external_id="e2", title="Post 2", post_text="text2", status="approved")
        )
        session.add(
            ChannelPost(channel_id="ch1", external_id="e3", title="Post 3", post_text="text3", status="rejected")
        )
        session.add(ChannelPost(channel_id="ch1", external_id="e4", title="Post 4", post_text="text4", status="draft"))

        await session.commit()

    return stats_session_maker


@pytest.mark.asyncio
async def test_get_channel_stats(seeded_session_maker: async_sessionmaker[AsyncSession]) -> None:
    stats = await get_channel_stats(seeded_session_maker, "ch1")
    assert stats["channel_id"] == "ch1"
    assert stats["total_posts"] == 4
    assert stats["approved"] == 2
    assert stats["rejected"] == 1
    assert stats["draft"] == 1
    assert stats["approval_rate"] == 0.5
    assert stats["active_sources"] == 2
    assert stats["disabled_sources"] == 1
    assert stats["avg_relevance_score"] > 0


@pytest.mark.asyncio
async def test_get_channel_stats_empty(stats_session_maker: async_sessionmaker[AsyncSession]) -> None:
    stats = await get_channel_stats(stats_session_maker, "nonexistent")
    assert stats["total_posts"] == 0
    assert stats["approval_rate"] == 0.0
    assert stats["active_sources"] == 0


@pytest.mark.asyncio
async def test_get_all_channels_stats(seeded_session_maker: async_sessionmaker[AsyncSession]) -> None:
    all_stats = await get_all_channels_stats(seeded_session_maker)
    assert len(all_stats) >= 1
    assert all_stats[0]["channel_id"] == "ch1"


@pytest.mark.asyncio
async def test_get_recent_posts(seeded_session_maker: async_sessionmaker[AsyncSession]) -> None:
    posts = await get_recent_posts(seeded_session_maker, "ch1", limit=2)
    assert len(posts) == 2
    # Most recent first
    assert all("title" in p and "status" in p for p in posts)


@pytest.mark.asyncio
async def test_get_sources(seeded_session_maker: async_sessionmaker[AsyncSession]) -> None:
    sources = await get_sources(seeded_session_maker, "ch1")
    assert len(sources) == 3
    # Ordered by relevance_score desc
    assert sources[0]["relevance_score"] >= sources[-1]["relevance_score"]


# -------------------------------------------------------------------------
# Route / integration tests (aiohttp test client)
# -------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def api_client(seeded_session_maker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[TestClient[Any, Any]]:
    """Create an aiohttp test client with seeded data."""
    clear_tokens()
    app = create_api_app(
        session_maker=seeded_session_maker,
        allowed_emails=["allowed@example.com"],
    )
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    clear_tokens()


@pytest.mark.asyncio
async def test_magic_link_endpoint(api_client: TestClient[Any, Any]) -> None:
    resp = await api_client.post(
        "/api/auth/magic-link",
        json={"email": "allowed@example.com"},
    )
    assert resp.status == 201
    data = await resp.json()
    assert "token" in data
    assert data["email"] == "allowed@example.com"
    assert data["role"] == "viewer"


@pytest.mark.asyncio
async def test_magic_link_forbidden_email(api_client: TestClient[Any, Any]) -> None:
    resp = await api_client.post(
        "/api/auth/magic-link",
        json={"email": "hacker@evil.com"},
    )
    assert resp.status == 403


@pytest.mark.asyncio
async def test_magic_link_missing_email(api_client: TestClient[Any, Any]) -> None:
    resp = await api_client.post("/api/auth/magic-link", json={})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_verify_valid_token(api_client: TestClient[Any, Any]) -> None:
    # Generate a token first
    token = generate_magic_link("allowed@example.com", role="admin")
    resp = await api_client.get(f"/api/auth/verify?token={token}")
    assert resp.status == 200
    data = await resp.json()
    assert data["authenticated"] is True
    assert data["email"] == "allowed@example.com"


@pytest.mark.asyncio
async def test_verify_invalid_token(api_client: TestClient[Any, Any]) -> None:
    resp = await api_client.get("/api/auth/verify?token=bad-token")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_stats_requires_auth(api_client: TestClient[Any, Any]) -> None:
    resp = await api_client.get("/api/stats/channels")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_stats_rejects_bad_token(api_client: TestClient[Any, Any]) -> None:
    resp = await api_client.get(
        "/api/stats/channels",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status == 401


@pytest.mark.asyncio
async def test_stats_channels_list(api_client: TestClient[Any, Any]) -> None:
    token = generate_magic_link("allowed@example.com")
    resp = await api_client.get(
        "/api/stats/channels",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["channel_id"] == "ch1"


@pytest.mark.asyncio
async def test_stats_channel_detail(api_client: TestClient[Any, Any]) -> None:
    token = generate_magic_link("allowed@example.com")
    resp = await api_client.get(
        "/api/stats/channels/ch1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["total_posts"] == 4


@pytest.mark.asyncio
async def test_stats_channel_posts(api_client: TestClient[Any, Any]) -> None:
    token = generate_magic_link("allowed@example.com")
    resp = await api_client.get(
        "/api/stats/channels/ch1/posts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    assert len(data) == 4


@pytest.mark.asyncio
async def test_stats_channel_sources(api_client: TestClient[Any, Any]) -> None:
    token = generate_magic_link("allowed@example.com")
    resp = await api_client.get(
        "/api/stats/channels/ch1/sources",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    assert len(data) == 3
