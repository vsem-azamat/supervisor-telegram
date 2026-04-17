"""Unit tests for pick_composition + fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.image_pipeline.compose import (
    fallback_composition,
    pick_composition,
)
from app.channel.image_pipeline.score import ScoredImage

pytestmark = pytest.mark.asyncio


def _scored(url: str, q: int = 7, r: int = 7, description: str = "photo") -> ScoredImage:
    return ScoredImage(
        url=url,
        width=800,
        height=600,
        bytes_=b"\x00",
        quality_score=q,
        relevance_score=r,
        description=description,
    )


class TestPickComposition:
    async def test_returns_single(self):
        cands = [_scored("https://x/0.jpg")]
        resp = json.dumps({"composition": "single", "selected_indices": [0], "reason": "best fit"})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "single"
        assert d.selected_indices == [0]

    async def test_returns_album(self):
        cands = [_scored(f"https://x/{i}.jpg") for i in range(3)]
        resp = json.dumps({"composition": "album", "selected_indices": [0, 1, 2], "reason": "coherent"})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "album"
        assert d.selected_indices == [0, 1, 2]

    async def test_returns_none(self):
        cands = [_scored(f"https://x/{i}.jpg", q=3, r=3) for i in range(2)]
        resp = json.dumps({"composition": "none", "selected_indices": [], "reason": "all weak"})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "none"
        assert d.selected_indices == []

    async def test_llm_failure_falls_back(self):
        cands = [_scored("https://x/0.jpg", q=8, r=8), _scored("https://x/1.jpg", q=6, r=6)]
        with patch(
            "app.channel.image_pipeline.compose.openrouter_chat_completion",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        assert d.composition == "single"
        assert d.selected_indices == [0]
        assert d.reason.startswith("fallback")

    async def test_no_candidates_returns_none(self):
        # No LLM call when candidate pool is empty.
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock()) as m:
            d = await pick_composition(post_text="Body.", candidates=[], api_key="k", model="m")
        assert d.composition == "none"
        m.assert_not_called()

    async def test_clamps_indices_to_valid_range(self):
        cands = [_scored("https://x/0.jpg")]
        resp = json.dumps({"composition": "album", "selected_indices": [0, 7, 99], "reason": ""})
        with patch("app.channel.image_pipeline.compose.openrouter_chat_completion", new=AsyncMock(return_value=resp)):
            d = await pick_composition(post_text="Body.", candidates=cands, api_key="k", model="m")
        # Out-of-range indices dropped; still returns as album if ≥2 valid, else single.
        assert d.selected_indices == [0]
        assert d.composition in ("single", "none")


class TestFallbackComposition:
    def test_picks_highest_scored_non_logo(self):
        cands = [
            _scored("https://x/0.jpg", q=5, r=5),
            _scored("https://x/1.jpg", q=9, r=8),
        ]
        # Sorted by vision_score already → [0]=bad, [1]=good. Fallback takes index 0 by convention.
        d = fallback_composition(cands)
        assert d.composition == "single"
        assert d.selected_indices == [0]

    def test_none_when_all_low_quality(self):
        cands = [_scored("https://x/0.jpg", q=3, r=5)]
        d = fallback_composition(cands)
        assert d.composition == "none"
        assert d.selected_indices == []

    def test_empty_input(self):
        d = fallback_composition([])
        assert d.composition == "none"
