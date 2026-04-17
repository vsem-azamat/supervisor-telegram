"""Unit tests: generator.generate_post wires into the new image_pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.channel.generator import generate_post
from app.channel.image_pipeline.models import CompositionDecision, ImageCandidate
from app.channel.sources import ContentItem

pytestmark = pytest.mark.asyncio


def _item() -> ContentItem:
    return ContentItem(source_url="https://src/a", external_id="x1", title="Students", body="Body.")


async def _fake_generate_agent_run(*args, **kwargs):
    """Stub Agent.run returning a minimal GeneratedPost."""
    from app.channel.generator import GeneratedPost

    class _Result:
        def __init__(self):
            self.output = GeneratedPost(text="Body text.\n\n——\n🔗 **Konnekt**", is_sensitive=False, image_urls=[])

        def usage(self):
            return None

    return _Result()


@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_generator_persists_candidates_and_selected_urls(mock_agent_factory, mock_usage, session_maker):
    """Generator populates image_urls AND image_candidates from the new pipeline."""
    agent = AsyncMock()
    agent.run = AsyncMock(side_effect=_fake_generate_agent_run)
    mock_agent_factory.return_value = agent

    pool = [
        ImageCandidate(
            url="https://x/a.jpg",
            source="og_image",
            quality_score=8,
            relevance_score=7,
            description="a",
            phash="aaaa",
            width=800,
            height=600,
            selected=False,
        ),
        ImageCandidate(
            url="https://x/b.jpg",
            source="article_body",
            quality_score=6,
            relevance_score=6,
            description="b",
            phash="bbbb",
            width=800,
            height=600,
            selected=False,
        ),
    ]
    decision = CompositionDecision(composition="single", selected_indices=[0], reason="best")

    with (
        patch("app.channel.generator.build_candidates", new=AsyncMock(return_value=pool)),
        patch("app.channel.generator.pick_composition", new=AsyncMock(return_value=decision)),
    ):
        post = await generate_post(
            [_item()],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=session_maker,
        )

    assert post is not None
    assert post.image_urls == ["https://x/a.jpg"]
    assert post.image_url == "https://x/a.jpg"
    assert post.image_candidates is not None
    assert len(post.image_candidates) == 2
    assert post.image_candidates[0]["selected"] is True
    assert post.image_candidates[1]["selected"] is False
    assert post.image_phashes == ["aaaa"]


@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_generator_with_none_composition(mock_agent_factory, mock_usage, session_maker):
    """composition='none' → image_urls=[], image_candidates still populated (pool kept)."""
    agent = AsyncMock()
    agent.run = AsyncMock(side_effect=_fake_generate_agent_run)
    mock_agent_factory.return_value = agent

    pool = [ImageCandidate(url="https://x/a.jpg", source="og_image", quality_score=3)]
    decision = CompositionDecision(composition="none", selected_indices=[], reason="all weak")

    with (
        patch("app.channel.generator.build_candidates", new=AsyncMock(return_value=pool)),
        patch("app.channel.generator.pick_composition", new=AsyncMock(return_value=decision)),
    ):
        post = await generate_post(
            [_item()],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=session_maker,
        )
    assert post is not None
    assert post.image_urls == []
    assert post.image_url is None
    assert post.image_candidates is not None
    assert len(post.image_candidates) == 1
    assert post.image_phashes == []


@patch("app.channel.generator.extract_usage_from_pydanticai_result", return_value=None)
@patch("app.channel.generator._create_generation_agent")
async def test_generator_handles_pipeline_failure(mock_agent_factory, mock_usage, session_maker):
    """Any exception from build_candidates → post still generated, no images."""
    agent = AsyncMock()
    agent.run = AsyncMock(side_effect=_fake_generate_agent_run)
    mock_agent_factory.return_value = agent

    with patch("app.channel.generator.build_candidates", new=AsyncMock(side_effect=RuntimeError("boom"))):
        post = await generate_post(
            [_item()],
            api_key="k",
            model="m",
            language="Russian",
            channel_id=-100,
            session_maker=session_maker,
        )
    assert post is not None
    assert post.image_urls == []
    assert post.image_candidates is None
