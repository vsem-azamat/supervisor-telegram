"""Integration test: generator → pipeline → DB persist round-trip (PG)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.channel.generator import GeneratedPost, generate_post
from app.channel.sources import ContentItem
from app.core.enums import PostStatus
from app.db.models import ChannelPost

from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _resp(data: bytes) -> httpx.Response:
    return httpx.Response(200, content=data, request=httpx.Request("GET", "https://x"))


def _good_vision(n: int) -> str:
    return json.dumps(
        [
            {
                "index": i,
                "quality_score": 8,
                "relevance_score": 8,
                "is_logo": False,
                "is_text_slide": False,
                "description": f"p{i}",
            }
            for i in range(n)
        ]
    )


def _compose_single() -> str:
    return json.dumps({"composition": "single", "selected_indices": [0], "reason": "best"})


async def test_full_happy_flow(pg_session_maker, monkeypatch):
    """End-to-end: build_candidates (real PG dedup) + pick_composition + generator + review persist."""
    data_a = make_test_image(width=900, height=700, colors=200, seed=1)

    async def fake_safe_fetch(url, **kwargs):
        return _resp(data_a)

    # Three LLM calls: generation (agent), vision_score, pick_composition.
    # Generation is the real agent — keep that working via monkeypatch on its run method.
    def fake_generate_agent_run(prompt, **kwargs):
        class R:
            output = GeneratedPost(text="Body text.\n\n——\n🔗 **Konnekt**", is_sensitive=False, image_urls=[])

            def all_messages(self):
                return []

        return R()

    class _FakeAgent:
        async def run(self, *a, **kw):
            return fake_generate_agent_run(*a, **kw)

    with (
        patch("app.channel.generator._create_generation_agent", return_value=_FakeAgent()),
        patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_safe_fetch)),
        patch("app.channel.images.is_safe_url", new=AsyncMock(return_value=True)),
        patch("app.channel.images.get_http_client") as mock_http,
        patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(return_value=_good_vision(1)),
        ),
        patch(
            "app.channel.image_pipeline.compose.openrouter_chat_completion",
            new=AsyncMock(return_value=_compose_single()),
        ),
    ):
        # Stub images.get_http_client so find_images_for_post returns one URL
        html_with_og = b'<meta property="og:image" content="https://x/a.jpg">'
        mock_resp = AsyncMock()
        mock_resp.text = html_with_og.decode()
        mock_resp.raise_for_status = lambda: None
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_http.return_value = mock_client

        item = ContentItem(
            source_url="https://src.example/article",
            external_id="e1",
            title="Students news",
            body="b",
            url="https://src.example/article",
        )
        post = await generate_post(
            [item],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=pg_session_maker,
            vision_model="vm",
        )

    assert post is not None
    assert post.image_urls == ["https://x/a.jpg"]
    assert post.image_candidates is not None
    assert len(post.image_candidates) == 1
    assert post.image_candidates[0]["selected"] is True
    assert post.image_phashes
    assert len(post.image_phashes[0]) == 16


async def test_second_generation_is_deduped(pg_session_maker):
    """Insert a prior post with phash of our canonical image → next pipeline run drops it."""
    from app.channel.image_pipeline.dedup import compute_phash

    data = make_test_image(width=900, height=700, colors=200, seed=1)
    async with pg_session_maker() as session:
        prior = ChannelPost(
            channel_id=-100,
            external_id="prior",
            title="t",
            post_text="b",
            status=PostStatus.APPROVED,
        )
        prior.image_phashes = [compute_phash(data)]
        session.add(prior)
        await session.commit()

    async def fake_safe_fetch(url, **kwargs):
        return _resp(data)

    class _FakeAgent:
        async def run(self, *a, **kw):
            class R:
                output = GeneratedPost(text="Body.\n\n——", is_sensitive=False, image_urls=[])

                def all_messages(self):
                    return []

            return R()

    with (
        patch("app.channel.generator._create_generation_agent", return_value=_FakeAgent()),
        patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None),
        patch("app.channel.image_pipeline.filter.safe_fetch", new=AsyncMock(side_effect=fake_safe_fetch)),
        patch("app.channel.images.is_safe_url", new=AsyncMock(return_value=True)),
        patch("app.channel.images.get_http_client") as mock_http,
        patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(return_value=_good_vision(1)),
        ),
        patch(
            "app.channel.image_pipeline.compose.openrouter_chat_completion",
            new=AsyncMock(return_value=_compose_single()),
        ),
    ):
        html_with_og = b'<meta property="og:image" content="https://x/a.jpg">'
        mock_resp = AsyncMock()
        mock_resp.text = html_with_og.decode()
        mock_resp.raise_for_status = lambda: None
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_http.return_value = mock_client

        item = ContentItem(
            source_url="https://src.example/article",
            external_id="e2",
            title="News",
            body="b",
            url="https://src.example/article",
        )
        post = await generate_post(
            [item],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=pg_session_maker,
            vision_model="vm",
        )

    # The candidate was a perfect duplicate → pipeline drops it → no images on the new post.
    assert post is not None
    assert post.image_urls == []
    assert post.image_candidates == []  # empty pool, not None
