"""Pydantic models for the image pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImageCandidate(BaseModel):
    """One scored image candidate — a row in the post's candidate pool.

    Persisted to ``ChannelPost.image_candidates`` as a list of dicts.
    Raw image ``bytes`` are *not* stored — they live in an in-memory cache
    during pipeline processing and are discarded afterwards.
    """

    url: str
    source: str  # "og_image" | "article_body" | "rss_enclosure" | "reviewer_added" | "brave_image"
    width: int | None = None
    height: int | None = None
    phash: str | None = None
    quality_score: int | None = Field(default=None, ge=0, le=10)
    relevance_score: int | None = Field(default=None, ge=0, le=10)
    is_logo: bool = False
    is_text_slide: bool = False
    is_duplicate: bool = False
    description: str = ""
    selected: bool = False

    model_config = ConfigDict(extra="ignore")


class VisionScore(BaseModel):
    """Per-image score returned by the vision model (one per input image)."""

    index: int
    quality_score: int = Field(ge=0, le=10)
    relevance_score: int = Field(ge=0, le=10)
    is_logo: bool
    is_text_slide: bool
    description: str


class CompositionDecision(BaseModel):
    """Output of ``pick_composition`` — final shape of the post's images."""

    composition: Literal["single", "album", "none"]
    selected_indices: list[int] = Field(default_factory=list)
    reason: str = ""
