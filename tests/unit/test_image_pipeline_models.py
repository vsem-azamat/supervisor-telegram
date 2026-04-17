"""Unit tests for image pipeline Pydantic models."""

from __future__ import annotations

import pytest
from app.channel.image_pipeline.models import (
    CompositionDecision,
    ImageCandidate,
    VisionScore,
)
from pydantic import ValidationError


class TestImageCandidate:
    def test_defaults(self):
        c = ImageCandidate(url="https://x/y.jpg", source="og_image")
        assert c.url == "https://x/y.jpg"
        assert c.source == "og_image"
        assert c.selected is False
        assert c.is_logo is False
        assert c.quality_score is None

    def test_json_roundtrip(self):
        c = ImageCandidate(
            url="https://x/y.jpg",
            source="article_body",
            width=800,
            height=600,
            phash="a3f8d2c1b9e47f05",
            quality_score=7,
            relevance_score=8,
            description="people in a lecture hall",
            selected=True,
        )
        dumped = c.model_dump()
        restored = ImageCandidate.model_validate(dumped)
        assert restored == c

    def test_model_ignores_unknown_fields(self):
        """image_candidates JSON from older schema versions must not break loading."""
        restored = ImageCandidate.model_validate(
            {"url": "https://x/y.jpg", "source": "og_image", "legacy_junk_field": "ignore_me"}
        )
        assert restored.url == "https://x/y.jpg"

    def test_score_range_validation(self):
        with pytest.raises(ValidationError):
            ImageCandidate(url="u", source="s", quality_score=11)
        with pytest.raises(ValidationError):
            ImageCandidate(url="u", source="s", relevance_score=-1)


class TestVisionScore:
    def test_minimal(self):
        v = VisionScore(
            index=0,
            quality_score=7,
            relevance_score=8,
            is_logo=False,
            is_text_slide=False,
            description="photo of a building",
        )
        assert v.index == 0
        assert v.description == "photo of a building"

    def test_requires_all_fields(self):
        with pytest.raises(ValidationError):
            VisionScore(index=0)  # type: ignore[call-arg]


class TestCompositionDecision:
    def test_defaults(self):
        d = CompositionDecision(composition="none")
        assert d.selected_indices == []
        assert d.reason == ""

    def test_rejects_invalid_composition(self):
        with pytest.raises(ValidationError):
            CompositionDecision(composition="carousel")  # type: ignore[arg-type]

    def test_full(self):
        d = CompositionDecision(composition="album", selected_indices=[0, 2, 3], reason="coherent photos")
        assert d.composition == "album"
        assert d.selected_indices == [0, 2, 3]
