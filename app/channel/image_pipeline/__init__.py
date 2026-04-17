"""Image pipeline package: filter → score → dedup → (compose externally).

Top-level orchestrator ``build_candidates`` runs the four-stage pipeline and
returns a list of ``ImageCandidate`` ready to be passed to ``pick_composition``
and persisted on ``ChannelPost.image_candidates``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channel.image_pipeline.compose import CompositionDecision, fallback_composition, pick_composition
from app.channel.image_pipeline.dedup import phash_dedup
from app.channel.image_pipeline.filter import cheap_filter
from app.channel.image_pipeline.models import (
    ImageCandidate,
    VisionScore,
)
from app.channel.image_pipeline.score import ScoredImage, vision_score
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.image_pipeline")

__all__ = [
    "CompositionDecision",
    "ImageCandidate",
    "ScoredImage",
    "VisionScore",
    "build_candidates",
    "fallback_composition",
    "pick_composition",
]


async def build_candidates(
    *,
    urls: list[str],
    title: str,
    channel_id: int,
    session_maker: async_sessionmaker[AsyncSession],
    api_key: str,
    vision_model: str,
    phash_threshold: int,
    phash_lookback: int,
    source_map: dict[str, str] | None = None,
) -> list[ImageCandidate]:
    """Run filter → score → dedup and return a list of Pydantic ImageCandidates.

    The returned list is the post's candidate pool: all inputs that survived
    filter + dedup, with scores attached where the vision model succeeded.
    Caller is responsible for ``pick_composition`` + persistence.

    ``source_map`` maps URL → source label ("og_image", "article_body",
    "rss_enclosure", ...). Missing URLs default to ``"article_body"``.
    """
    if not urls:
        return []

    source_map = source_map or {}

    # Stage 1: cheap filter (download + Pillow heuristics)
    filtered = await cheap_filter(urls)
    if not filtered:
        logger.info("image_pipeline_no_candidates_after_filter", channel_id=channel_id, input=len(urls))
        return []

    # Stage 2: vision scoring (batched multimodal call).
    # vision_score drops is_logo/is_text_slide/low-score; that is desired —
    # the reviewer can always re-add via `add_image_url` if they disagree.
    # On API failure it returns every candidate with null scores instead,
    # so `scored` is never empty when `filtered` wasn't.
    scored = await vision_score(filtered, title=title, api_key=api_key, model=vision_model)
    if not scored:
        logger.info("image_pipeline_no_candidates_after_vision", channel_id=channel_id, input=len(filtered))
        return []

    # Stage 3: phash dedup — mutates .phash and .is_duplicate, returns non-dups.
    from app.channel.image_pipeline.filter import FilteredImage

    filtered_for_dedup = [FilteredImage(url=s.url, width=s.width, height=s.height, bytes_=s.bytes_) for s in scored]
    unique = await phash_dedup(
        session_maker,
        channel_id,
        filtered_for_dedup,
        threshold=phash_threshold,
        lookback=phash_lookback,
    )
    unique_urls = {u.url: u for u in unique}

    # Stitch scores back onto deduped candidates
    pool: list[ImageCandidate] = []
    for s in scored:
        f = unique_urls.get(s.url)
        if f is None:
            continue  # was a duplicate
        pool.append(
            ImageCandidate(
                url=s.url,
                source=source_map.get(s.url, "article_body"),
                width=s.width,
                height=s.height,
                phash=f.phash,
                quality_score=s.quality_score,
                relevance_score=s.relevance_score,
                is_logo=s.is_logo,
                is_text_slide=s.is_text_slide,
                is_duplicate=False,
                description=s.description,
                selected=False,
            )
        )

    logger.info(
        "image_pipeline_pool_built",
        channel_id=channel_id,
        input=len(urls),
        post_filter=len(filtered),
        post_dedup=len(pool),
    )
    return pool
