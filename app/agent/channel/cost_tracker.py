"""LLM cost tracking for channel agent — in-memory accumulation + structured logging."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.logging import get_logger

logger = get_logger("channel.cost_tracker")

# Rough per-1k-token pricing for known models (USD).
MODEL_COSTS: dict[str, dict[str, float]] = {
    "google/gemini-2.0-flash-001": {"input": 0.0001, "output": 0.0004},
    "google/gemini-3.1-pro-preview": {"input": 0.00025, "output": 0.001},
    "google/gemini-3.1-flash-lite-preview": {"input": 0.00005, "output": 0.0002},
    "perplexity/sonar": {"input": 0.001, "output": 0.001},
}

_DEFAULT_COST = {"input": 0.001, "output": 0.001}


@dataclass
class LLMUsage:
    """Single LLM call usage record."""

    model: str
    operation: str  # screening, generation, discovery, feedback, edit, source_discovery
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    channel_id: str | None = None
    created_at: datetime = field(default_factory=datetime.now)


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    costs = MODEL_COSTS.get(model, _DEFAULT_COST)
    input_cost = (prompt_tokens / 1000) * costs["input"]
    output_cost = (completion_tokens / 1000) * costs["output"]
    return round(input_cost + output_cost, 8)


def extract_usage_from_openrouter_response(
    response_json: dict[str, Any],
    model: str,
    operation: str,
    channel_id: str | None = None,
) -> LLMUsage | None:
    """Extract usage data from a raw OpenRouter API response."""
    usage = response_json.get("usage")
    if not usage:
        return None

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

    return LLMUsage(
        model=model,
        operation=operation,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=_estimate_cost(model, prompt_tokens, completion_tokens),
        channel_id=channel_id,
    )


def extract_usage_from_pydanticai_result(
    result: Any,
    model: str,
    operation: str,
    channel_id: str | None = None,
) -> LLMUsage | None:
    """Extract usage data from a PydanticAI agent result.

    PydanticAI results expose ``result.usage()`` returning a ``Usage`` object
    with ``request_tokens``, ``response_tokens``, and ``total_tokens``.
    """
    try:
        usage = result.usage()
    except Exception:
        return None

    if usage is None:
        return None

    prompt_tokens = getattr(usage, "request_tokens", 0) or 0
    completion_tokens = getattr(usage, "response_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or (
        prompt_tokens + completion_tokens
    )

    return LLMUsage(
        model=model,
        operation=operation,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=_estimate_cost(model, prompt_tokens, completion_tokens),
        channel_id=channel_id,
    )


# ── In-memory accumulator ────────────────────────────────────────────

_MAX_USAGE_HISTORY = 1000

_usage_history: list[LLMUsage] = []


async def log_usage(usage: LLMUsage) -> None:
    """Log a single LLM usage record and accumulate it in memory.

    The in-memory history is capped at :data:`_MAX_USAGE_HISTORY` entries.
    When the cap is reached, the oldest entries are evicted.
    """
    _usage_history.append(usage)
    # Evict oldest entries to prevent unbounded memory growth
    if len(_usage_history) > _MAX_USAGE_HISTORY:
        _usage_history[:] = _usage_history[-_MAX_USAGE_HISTORY:]
    logger.info(
        "llm_usage",
        model=usage.model,
        operation=usage.operation,
        tokens=usage.total_tokens,
        cost_usd=usage.estimated_cost_usd,
        channel_id=usage.channel_id,
    )


def get_session_summary() -> dict[str, Any]:
    """Return accumulated usage summary: total tokens, cost, and per-operation breakdown."""
    total_tokens = 0
    total_cost = 0.0
    by_operation: dict[str, dict[str, float | int]] = {}

    for u in _usage_history:
        total_tokens += u.total_tokens
        total_cost += u.estimated_cost_usd

        if u.operation not in by_operation:
            by_operation[u.operation] = {"tokens": 0, "cost_usd": 0.0, "calls": 0}

        by_operation[u.operation]["tokens"] += u.total_tokens
        by_operation[u.operation]["cost_usd"] += u.estimated_cost_usd
        by_operation[u.operation]["calls"] += 1

    return {
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 8),
        "total_calls": len(_usage_history),
        "by_operation": by_operation,
    }


def reset_usage_history() -> None:
    """Clear accumulated usage history (useful for testing)."""
    _usage_history.clear()
