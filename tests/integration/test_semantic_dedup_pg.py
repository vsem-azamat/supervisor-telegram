"""Integration tests for semantic_dedup against real Postgres + pgvector.

Closes the biggest untested gap: the `embedding <=> vector` cosine-distance
query was fully mocked in every existing test because SQLite can't load the
pgvector extension. These tests verify the SQL against a real pgvector
container and catch regressions in threshold / lookback / channel-isolation
logic.

LLM embeddings API is mocked (deterministic vectors in tests). Everything
else hits real code paths + real database.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from app.channel.semantic_dedup import filter_semantic_duplicates, find_nearest_posts
from app.channel.sources import ContentItem
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import ChannelPost

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CHANNEL_ID = -100123456789


def _vector(base: float, dim: int = 768) -> list[float]:
    """Deterministic normalized-ish vector for testing cosine similarity."""
    v = [base] * dim
    norm = (sum(x * x for x in v)) ** 0.5
    return [x / norm for x in v]


def _near_vector(base: float, perturbation: float, dim: int = 768) -> list[float]:
    """A vector very close to _vector(base) — cosine distance ≈ perturbation²/2."""
    v = [base] * dim
    v[0] += perturbation
    norm = (sum(x * x for x in v)) ** 0.5
    return [x / norm for x in v]


async def _insert_post(session_maker, *, title: str, embedding: list[float], age_days: int = 0) -> int:
    """Insert a ChannelPost with an embedding. Returns its id."""
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=_CHANNEL_ID,
            external_id=title.replace(" ", "_").lower(),
            title=title,
            post_text=f"Body of {title}",
            status=PostStatus.APPROVED,
            embedding=embedding,
            embedding_model="test-model",
        )
        if age_days:
            post.created_at = utc_now() - timedelta(days=age_days)
        session.add(post)
        await session.commit()
        return post.id


class TestFilterSemanticDuplicates:
    async def test_exact_match_is_filtered(self, pg_session_maker):
        """Identical vectors → cosine distance 0 → filtered as duplicate."""
        stored_vec = _vector(1.0)
        await _insert_post(pg_session_maker, title="Existing post", embedding=stored_vec)

        items = [ContentItem(source_url="rss://feed1", external_id="new1", title="Same topic", body="x")]

        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [stored_vec]

            remaining = await filter_semantic_duplicates(
                items,
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
                threshold=0.85,
            )

        assert remaining == []

    async def test_distinct_vector_passes(self, pg_session_maker):
        """Orthogonal-ish vectors → distance > threshold → not filtered."""
        await _insert_post(pg_session_maker, title="Existing post", embedding=_vector(1.0))

        # Completely different direction in 768-dim space
        other_vec = [0.0] * 768
        other_vec[100] = 1.0  # Unit vector along axis 100

        items = [ContentItem(source_url="rss://feed1", external_id="new1", title="Different topic", body="y")]

        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [other_vec]

            remaining = await filter_semantic_duplicates(
                items,
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
                threshold=0.85,
            )

        assert len(remaining) == 1
        assert remaining[0].external_id == "new1"

    async def test_other_channel_does_not_cross_contaminate(self, pg_session_maker):
        """Dedup must be scoped per channel — posts in channel A don't block channel B."""
        other_channel = _CHANNEL_ID - 1
        stored_vec = _vector(1.0)
        async with pg_session_maker() as session:
            session.add(
                ChannelPost(
                    channel_id=other_channel,
                    external_id="other_post",
                    title="Other channel's post",
                    post_text="x",
                    status=PostStatus.APPROVED,
                    embedding=stored_vec,
                    embedding_model="test-model",
                )
            )
            await session.commit()

        items = [ContentItem(source_url="rss://feed1", external_id="new1", title="Same topic", body="x")]

        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [stored_vec]

            remaining = await filter_semantic_duplicates(
                items,
                channel_id=_CHANNEL_ID,  # queried channel, NOT other_channel
                api_key="test",
                session_maker=pg_session_maker,
                threshold=0.85,
            )

        assert len(remaining) == 1, "items in other_channel should not filter out items in _CHANNEL_ID"

    async def test_old_posts_outside_lookback_do_not_filter(self, pg_session_maker):
        """Posts older than lookback_days should not be considered for dedup."""
        stored_vec = _vector(1.0)
        await _insert_post(pg_session_maker, title="Very old post", embedding=stored_vec, age_days=30)

        items = [ContentItem(source_url="rss://feed1", external_id="new1", title="Same topic", body="x")]

        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [stored_vec]

            remaining = await filter_semantic_duplicates(
                items,
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
                threshold=0.85,
                lookback_days=7,  # 30-day-old post is outside window
            )

        assert len(remaining) == 1, "post older than lookback_days must not dedupe"

    async def test_empty_input_returns_empty(self, pg_session_maker):
        """Empty input list short-circuits with no API call."""
        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            remaining = await filter_semantic_duplicates(
                [],
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
            )
        assert remaining == []
        mock_embed.assert_not_called()

    async def test_mixed_batch_partial_filtering(self, pg_session_maker):
        """Batch of 3 items where only 1 is a duplicate — 2 should pass through."""
        stored_vec = _vector(1.0)
        await _insert_post(pg_session_maker, title="Existing", embedding=stored_vec)

        unique_a = [0.0] * 768
        unique_a[50] = 1.0
        unique_b = [0.0] * 768
        unique_b[200] = 1.0

        items = [
            ContentItem(source_url="rss", external_id="dup", title="Dup", body="x"),
            ContentItem(source_url="rss", external_id="a", title="A", body="y"),
            ContentItem(source_url="rss", external_id="b", title="B", body="z"),
        ]

        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [stored_vec, unique_a, unique_b]

            remaining = await filter_semantic_duplicates(
                items,
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
                threshold=0.85,
            )

        kept_ids = {item.external_id for item in remaining}
        assert kept_ids == {"a", "b"}


class TestFindNearestPosts:
    async def test_returns_ordered_by_similarity(self, pg_session_maker):
        """find_nearest_posts ranks stored posts by cosine similarity to query."""
        base_vec = _vector(1.0)
        close_vec = _near_vector(1.0, perturbation=0.01)  # very close
        far_vec = [0.0] * 768
        far_vec[300] = 1.0

        await _insert_post(pg_session_maker, title="Close post", embedding=close_vec)
        await _insert_post(pg_session_maker, title="Far post", embedding=far_vec)

        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [base_vec]

            results = await find_nearest_posts(
                "some query text",
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
                limit=5,
            )

        assert len(results) == 2
        # First result should be the closer vector
        assert results[0][0] == "Close post"
        assert results[1][0] == "Far post"
        # Similarity scores should be descending
        assert results[0][1] > results[1][1]

    async def test_respects_limit(self, pg_session_maker):
        """limit parameter caps the number of returned rows."""
        for i in range(5):
            vec = [0.0] * 768
            vec[i] = 1.0
            await _insert_post(pg_session_maker, title=f"Post {i}", embedding=vec)

        query_vec = _vector(1.0)
        with patch("app.channel.semantic_dedup.get_embeddings") as mock_embed:
            mock_embed.return_value = [query_vec]

            results = await find_nearest_posts(
                "query",
                channel_id=_CHANNEL_ID,
                api_key="test",
                session_maker=pg_session_maker,
                limit=3,
            )

        assert len(results) == 3
