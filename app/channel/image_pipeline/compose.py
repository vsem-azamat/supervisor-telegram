"""Stage 4 of the image pipeline: LLM composition decision.

Given the generated post text and up to 5 scored candidates (metadata only,
not images), asks the model to pick ``single`` / ``album`` / ``none`` and the
indices to use. Falls back to a deterministic heuristic on any failure.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.channel.image_pipeline.models import CompositionDecision
from app.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.channel.image_pipeline.score import ScoredImage

logger = get_logger("channel.image_pipeline.compose")

MAX_ALBUM_SIZE = 4
FALLBACK_MIN_QUALITY = 5

_SYSTEM_PROMPT = """\
You are a visual editor for a Telegram news channel. Given a post and up to
5 candidate images with metadata, decide the final composition.

Return EXACTLY one JSON object:
{
  "composition": "single" | "album" | "none",
  "selected_indices": [int, ...],
  "reason": string
}

Rules:
- "none": no candidate is good enough, or all are off-topic/low-quality.
- "single": one strong image carrying the post's main visual.
- "album": 2-4 images that together tell the story AND share a coherent
  style. Do NOT mix a screenshot with a photograph, or unrelated scenes.
- Max 4 images in an album. Fewer is better — don't pad.
- When unsure, prefer "single" over weak "album", and "none" over bad "single".

No commentary, no markdown, no code fences.
"""


async def pick_composition(
    *,
    post_text: str,
    candidates: list[ScoredImage],
    api_key: str,
    model: str,
) -> CompositionDecision:
    """LLM picks the final composition; falls back to a heuristic on failure."""
    if not candidates:
        return CompositionDecision(composition="none", selected_indices=[], reason="no candidates")

    user_body = _build_user_payload(post_text, candidates)

    try:
        raw = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_body},
            ],
            operation="pick_composition",
            temperature=0.1,
            timeout=15,
        )
    except Exception:
        logger.warning("pick_composition_api_error", exc_info=True)
        return fallback_composition(candidates)

    if not raw:
        logger.warning("pick_composition_empty_response")
        return fallback_composition(candidates)

    try:
        parsed = json.loads(raw if isinstance(raw, str) else json.dumps(raw))
        decision = CompositionDecision.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError):
        logger.warning("pick_composition_parse_error", raw_snippet=str(raw)[:300], exc_info=True)
        return fallback_composition(candidates)

    # Clamp indices + enforce consistency between composition and count
    n = len(candidates)
    valid_indices = [i for i in decision.selected_indices if 0 <= i < n]
    if len(valid_indices) > MAX_ALBUM_SIZE:
        valid_indices = valid_indices[:MAX_ALBUM_SIZE]

    if not valid_indices:
        return CompositionDecision(
            composition="none", selected_indices=[], reason=decision.reason or "no valid indices"
        )
    if len(valid_indices) == 1:
        return CompositionDecision(composition="single", selected_indices=valid_indices, reason=decision.reason)
    return CompositionDecision(composition="album", selected_indices=valid_indices, reason=decision.reason)


def fallback_composition(candidates: list[ScoredImage]) -> CompositionDecision:
    """Deterministic fallback: highest-quality non-junk candidate as a single."""
    good = [
        c
        for c in candidates
        if (c.quality_score or 0) >= FALLBACK_MIN_QUALITY and not c.is_logo and not c.is_text_slide
    ]
    if not good:
        return CompositionDecision(
            composition="none", selected_indices=[], reason="fallback: no high-quality candidates"
        )
    # Pool is already sorted by score in vision_score, so index 0 is the best.
    best_idx = candidates.index(good[0])
    return CompositionDecision(
        composition="single",
        selected_indices=[best_idx],
        reason="fallback: used highest-scored candidate",
    )


def _build_user_payload(post_text: str, candidates: list[ScoredImage]) -> str:
    lines = [f"Post text:\n---\n{post_text}\n---", "", "Candidates:"]
    for i, c in enumerate(candidates):
        lines.append(f"  {i}: quality={c.quality_score} relevance={c.relevance_score} — {c.description}")
    return "\n".join(lines)
