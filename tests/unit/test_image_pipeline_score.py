"""Unit tests for the batched vision-model scorer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.image_pipeline.filter import FilteredImage
from app.channel.image_pipeline.score import ScoredImage, vision_score

from tests.fixtures.images import make_test_image

pytestmark = pytest.mark.asyncio


def _img(url: str) -> FilteredImage:
    data = make_test_image(width=800, height=600, colors=100)
    return FilteredImage(url=url, width=800, height=600, bytes_=data)


def _good_response(n: int) -> str:
    items = [
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
    return json.dumps(items)


class TestVisionScore:
    async def test_happy_path_keeps_all_and_sorts(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(3)]
        resp = json.dumps(
            [
                {
                    "index": 0,
                    "quality_score": 4,
                    "relevance_score": 8,
                    "is_logo": False,
                    "is_text_slide": False,
                    "description": "a",
                },
                {
                    "index": 1,
                    "quality_score": 9,
                    "relevance_score": 8,
                    "is_logo": False,
                    "is_text_slide": False,
                    "description": "b",
                },
                {
                    "index": 2,
                    "quality_score": 7,
                    "relevance_score": 6,
                    "is_logo": False,
                    "is_text_slide": False,
                    "description": "c",
                },
            ]
        )
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        # index 0 has quality_score=4 → dropped; remaining sorted by (q + r) desc
        assert [s.url for s in out] == ["https://x/1.jpg", "https://x/2.jpg"]
        assert all(isinstance(s, ScoredImage) for s in out)
        assert out[0].quality_score == 9
        assert out[0].description == "b"

    async def test_drops_is_logo_and_is_text_slide(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(2)]
        resp = json.dumps(
            [
                {
                    "index": 0,
                    "quality_score": 9,
                    "relevance_score": 9,
                    "is_logo": True,
                    "is_text_slide": False,
                    "description": "logo",
                },
                {
                    "index": 1,
                    "quality_score": 8,
                    "relevance_score": 7,
                    "is_logo": False,
                    "is_text_slide": True,
                    "description": "slide",
                },
            ]
        )
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert out == []

    async def test_drops_low_relevance(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(2)]
        resp = json.dumps(
            [
                {
                    "index": 0,
                    "quality_score": 9,
                    "relevance_score": 2,
                    "is_logo": False,
                    "is_text_slide": False,
                    "description": "irrelevant",
                },
                {
                    "index": 1,
                    "quality_score": 7,
                    "relevance_score": 5,
                    "is_logo": False,
                    "is_text_slide": False,
                    "description": "on-topic",
                },
            ]
        )
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert [s.url for s in out] == ["https://x/1.jpg"]

    async def test_api_failure_returns_unscored_copy(self):
        imgs = [_img(f"https://x/{i}.jpg") for i in range(2)]
        with patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert len(out) == 2
        assert all(s.quality_score is None for s in out)
        assert all(s.description == "" for s in out)

    async def test_malformed_json_returns_unscored(self):
        imgs = [_img("https://x/0.jpg")]
        with patch(
            "app.channel.image_pipeline.score.openrouter_chat_completion",
            new=AsyncMock(return_value="not json at all"),
        ):
            out = await vision_score(imgs, title="Test", api_key="k", model="m")
        assert len(out) == 1
        assert out[0].quality_score is None

    async def test_empty_input_short_circuits(self):
        with patch("app.channel.image_pipeline.score.openrouter_chat_completion", new=AsyncMock()) as m:
            out = await vision_score([], title="Test", api_key="k", model="m")
        assert out == []
        m.assert_not_called()
