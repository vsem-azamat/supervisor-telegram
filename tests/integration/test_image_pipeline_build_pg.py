"""Integration test: build_candidates end-to-end against real Postgres."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.channel.image_pipeline import build_candidates
from app.channel.image_pipeline.models import ImageCandidate
from app.core.enums import PostStatus
from app.db.models import ChannelPost

from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CHANNEL = -100888999


def _resp(data: bytes) -> httpx.Response:
    return httpx.Response(200, content=data, request=httpx.Request("GET", "https://x"))


def _good_vision_batch(n: int) -> str:
    import json

    return json.dumps(
        [
            {
                "index": i,
                "quality_score": 8,
                "relevance_score": 7,
                "is_logo": False,
                "is_text_slide": False,
                "description": f"photo {i}",
            }
            for i in range(n)
        ]
    )


class TestBuildCandidates:
    async def test_happy_flow(self, pg_session_maker):
        """Two URLs → both pass filter → both scored → no duplicates → pool of 2."""
        data_a = make_test_image(width=900, height=700, colors=200, seed=1)
        data_b = make_test_image(width=900, height=700, colors=200, seed=2)

        async def fake_fetch(url, **kwargs):
            return _resp(data_a if "a" in url else data_b)

        with (
            patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "app.channel.image_pipeline.score.openrouter_chat_completion",
                new=AsyncMock(return_value=_good_vision_batch(2)),
            ),
        ):
            out = await build_candidates(
                urls=["https://x/a.jpg", "https://x/b.jpg"],
                title="Students in Prague",
                channel_id=_CHANNEL,
                session_maker=pg_session_maker,
                api_key="k",
                vision_model="m",
                phash_threshold=10,
                phash_lookback=30,
            )
        assert len(out) == 2
        assert all(isinstance(c, ImageCandidate) for c in out)
        assert all(c.quality_score == 8 for c in out)
        assert all(c.phash is not None for c in out)

    async def test_existing_phash_drops_duplicate(self, pg_session_maker):
        """Insert a prior post with phash of image A; when A comes in again it's dedup'd."""
        from app.channel.image_pipeline.dedup import compute_phash

        data_a = make_test_image(width=900, height=700, colors=200, seed=1)
        data_b = make_test_image(width=900, height=700, colors=200, seed=2)
        async with pg_session_maker() as session:
            prior = ChannelPost(
                channel_id=_CHANNEL,
                external_id="prior",
                title="t",
                post_text="b",
                status=PostStatus.APPROVED,
            )
            prior.image_phashes = [compute_phash(data_a)]
            session.add(prior)
            await session.commit()

        async def fake_fetch(url, **kwargs):
            return _resp(data_a if "a" in url else data_b)

        with (
            patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "app.channel.image_pipeline.score.openrouter_chat_completion",
                new=AsyncMock(return_value=_good_vision_batch(2)),
            ),
        ):
            out = await build_candidates(
                urls=["https://x/a.jpg", "https://x/b.jpg"],
                title="Students",
                channel_id=_CHANNEL,
                session_maker=pg_session_maker,
                api_key="k",
                vision_model="m",
                phash_threshold=10,
                phash_lookback=30,
            )
        assert len(out) == 1
        assert out[0].url == "https://x/b.jpg"

    async def test_vision_failure_still_returns_candidates(self, pg_session_maker):
        """Vision API dead → candidates come back without scores (for fallback composition)."""
        data = make_test_image(width=900, height=700, colors=200, seed=1)

        async def fake_fetch(url, **kwargs):
            return _resp(data)

        with (
            patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_fetch)),
            patch(
                "app.channel.image_pipeline.score.openrouter_chat_completion",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            out = await build_candidates(
                urls=["https://x/a.jpg"],
                title="T",
                channel_id=_CHANNEL,
                session_maker=pg_session_maker,
                api_key="k",
                vision_model="m",
                phash_threshold=10,
                phash_lookback=30,
            )
        # Vision failed → candidates come back with null quality_score, but cheap_filter + phash still ran
        assert len(out) == 1
        assert out[0].quality_score is None
        assert out[0].phash is not None

    async def test_empty_urls_short_circuits(self, pg_session_maker):
        out = await build_candidates(
            urls=[],
            title="T",
            channel_id=_CHANNEL,
            session_maker=pg_session_maker,
            api_key="k",
            vision_model="m",
            phash_threshold=10,
            phash_lookback=30,
        )
        assert out == []
