"""Stage 2 of the image pipeline: vision-model quality/relevance scoring.

A single batched OpenRouter multimodal call (max 5 images) with a strict
JSON schema. Failures are swallowed — every candidate gets returned with
``quality_score=None`` so downstream stages can still proceed.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

if TYPE_CHECKING:
    from app.channel.image_pipeline.filter import FilteredImage

from app.channel.image_pipeline.models import VisionScore
from app.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger

logger = get_logger("channel.image_pipeline.score")

MIN_QUALITY = 5
MIN_RELEVANCE = 4
MAX_BATCH = 5

_SYSTEM_PROMPT = """\
You are an image quality reviewer for a Telegram news channel.
You will receive a post headline and up to 5 candidate images.

For EACH image return a JSON object:
{
  "index": int,
  "quality_score": 0-10,
  "relevance_score": 0-10,
  "is_logo": bool,
  "is_text_slide": bool,
  "description": string
}

Scoring rules:
- "quality_score" rates the photo itself: sharpness, composition, colour.
- "relevance_score" rates how well the image matches the headline topic.
- "is_logo" = true for company/brand marks, favicons, flat icons.
- "is_text_slide" = true if the image is mostly a text overlay, chart-with-text,
  or "breaking news" style banner. A real photo with some caption text is NOT
  a text slide.
- "description" is 4-8 words describing what is shown.

Return ONLY a JSON array of N objects, one per image, ordered by index 0..N-1.
No commentary, no markdown, no code fences.
"""


@dataclass(slots=True)
class ScoredImage:
    """A FilteredImage annotated with vision-model scores."""

    url: str
    width: int
    height: int
    bytes_: bytes
    quality_score: int | None = None
    relevance_score: int | None = None
    is_logo: bool = False
    is_text_slide: bool = False
    description: str = ""


async def vision_score(
    images: list[FilteredImage],
    *,
    title: str,
    api_key: str,
    model: str,
) -> list[ScoredImage]:
    """Rate up to MAX_BATCH candidates. Returns a filtered + sorted list.

    Failure modes all produce a ``ScoredImage`` per input with null scores;
    the downstream ``pick_composition`` has its own fallback.
    """
    if not images:
        return []

    batch = images[:MAX_BATCH]
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": f"Topic: {title}\n\nImages follow in order 0..{len(batch) - 1}."}
    ]
    for img in batch:
        b64 = base64.b64encode(img.bytes_).decode("ascii")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    try:
        raw = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            operation="vision_score",
            temperature=0.0,
            timeout=20,
        )
    except Exception:
        logger.warning("vision_score_api_error", count=len(batch), exc_info=True)
        return [_unscored(img) for img in batch]

    if not raw:
        logger.warning("vision_score_empty_response", count=len(batch))
        return [_unscored(img) for img in batch]

    try:
        parsed = json.loads(raw if isinstance(raw, str) else json.dumps(raw))
        if not isinstance(parsed, list):
            raise TypeError(f"expected list, got {type(parsed).__name__}")
        scores: dict[int, VisionScore] = {}
        for item in parsed:
            vs = VisionScore.model_validate(item)
            scores[vs.index] = vs
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning("vision_score_parse_error", raw_snippet=str(raw)[:300], exc_info=True)
        return [_unscored(img) for img in batch]

    annotated: list[ScoredImage] = []
    for i, img in enumerate(batch):
        s = scores.get(i)
        if s is None:
            annotated.append(_unscored(img))
            continue
        annotated.append(
            ScoredImage(
                url=img.url,
                width=img.width,
                height=img.height,
                bytes_=img.bytes_,
                quality_score=s.quality_score,
                relevance_score=s.relevance_score,
                is_logo=s.is_logo,
                is_text_slide=s.is_text_slide,
                description=s.description,
            )
        )

    # Post-processing
    kept = [
        s
        for s in annotated
        if not s.is_logo
        and not s.is_text_slide
        and (s.quality_score or 0) >= MIN_QUALITY
        and (s.relevance_score or 0) >= MIN_RELEVANCE
    ]
    kept.sort(key=lambda s: (s.quality_score or 0) + (s.relevance_score or 0), reverse=True)
    return kept


def _unscored(img: FilteredImage) -> ScoredImage:
    return ScoredImage(
        url=img.url,
        width=img.width,
        height=img.height,
        bytes_=img.bytes_,
    )
