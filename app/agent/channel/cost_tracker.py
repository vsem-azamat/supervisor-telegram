"""LLM cost tracking for channel agent — in-memory accumulation + structured logging."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime  # noqa: TC003 - needed at runtime for dataclass field type
from typing import Any

from app.core.logging import get_logger
from app.core.time import utc_now

logger = get_logger("channel.cost_tracker")

# Per-1k-token pricing (USD) from OpenRouter, updated 2026-03-07.
# "cache_read" = price per 1k cached-input tokens.
MODEL_COSTS: dict[str, dict[str, float]] = {
    # Classification only (spam detection, screening) — NOT for agentic/chat use.
    "google/gemini-2.0-flash-001": {"input": 0.0001, "output": 0.0004, "cache_read": 0.000025, "cache_write": 0.0001},
    "google/gemini-3.1-pro-preview": {
        "input": 0.002,
        "output": 0.012,
        "cache_read": 0.0002,
        "cache_write": 0.000375,
    },
    "google/gemini-3.1-flash-lite-preview": {
        "input": 0.00025,
        "output": 0.0015,
        "cache_read": 0.000025,
        "cache_write": 0.001,
    },
    "perplexity/sonar": {"input": 0.001, "output": 0.001, "cache_read": 0.001, "cache_write": 0.001},
    "anthropic/claude-sonnet-4-6": {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_write": 0.00375},
    "anthropic/claude-haiku-4-5": {"input": 0.001, "output": 0.005, "cache_read": 0.0001, "cache_write": 0.00125},
}

_DEFAULT_COST = {"input": 0.001, "output": 0.001, "cache_read": 0.0001, "cache_write": 0.001}


@dataclass
class LLMUsage:
    """Single LLM call usage record."""

    model: str
    operation: str  # screening, generation, discovery, feedback, edit, source_discovery
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_savings_usd: float = 0.0
    channel_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)


def _estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> tuple[float, float]:
    """Estimate USD cost and cache savings from token counts.

    Returns (actual_cost, savings_vs_no_cache).
    """
    costs = MODEL_COSTS.get(model, _DEFAULT_COST)

    # Non-cached input tokens = total input minus cached
    regular_input = max(0, prompt_tokens - cache_read_tokens - cache_write_tokens)

    input_cost = (regular_input / 1000) * costs["input"]
    output_cost = (completion_tokens / 1000) * costs["output"]
    cache_read_cost = (cache_read_tokens / 1000) * costs.get("cache_read", costs["input"])
    cache_write_cost = (cache_write_tokens / 1000) * costs.get("cache_write", costs["input"])

    actual_cost = round(input_cost + output_cost + cache_read_cost + cache_write_cost, 8)

    # What it WOULD have cost without caching (all input at full price)
    no_cache_cost = (prompt_tokens / 1000) * costs["input"] + (completion_tokens / 1000) * costs["output"]
    savings = round(max(0.0, no_cache_cost - actual_cost), 8)

    return actual_cost, savings


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

    # OpenRouter returns cache info in prompt_tokens_details
    details = usage.get("prompt_tokens_details") or {}
    cache_read = details.get("cached_tokens", 0)

    # Some providers put it directly in usage
    if not cache_read:
        cache_read = usage.get("cache_read_input_tokens", 0) or usage.get("prompt_cache_hit_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0) or usage.get("prompt_cache_miss_tokens", 0)

    cost, savings = _estimate_cost(model, prompt_tokens, completion_tokens, cache_read, cache_write)

    return LLMUsage(
        model=model,
        operation=operation,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cache_savings_usd=savings,
        channel_id=channel_id,
    )


def extract_usage_from_pydanticai_result(
    result: Any,
    model: str,
    operation: str,
    channel_id: str | None = None,
) -> LLMUsage | None:
    """Extract usage data from a PydanticAI agent result.

    PydanticAI results expose ``result.usage()`` returning a ``RunUsage`` object
    with ``request_tokens``, ``response_tokens``, ``cache_read_tokens``, etc.
    """
    try:
        usage = result.usage()
    except Exception:
        return None

    if usage is None:
        return None

    def _int(val: Any) -> int:
        if val is None or val is False:
            return 0
        if isinstance(val, (int, float)):
            return int(val)
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    def _get_token_field(obj: Any, *field_names: str) -> int:
        """Get first valid integer field from an object, trying field names in order."""
        for name in field_names:
            val = getattr(obj, name, None)
            if isinstance(val, (int, float)):
                return int(val)
        return 0

    prompt_tokens = _get_token_field(usage, "input_tokens", "request_tokens")
    completion_tokens = _get_token_field(usage, "output_tokens", "response_tokens")
    total_tokens = _int(getattr(usage, "total_tokens", 0)) or (prompt_tokens + completion_tokens)
    cache_read = _int(getattr(usage, "cache_read_tokens", 0))
    cache_write = _int(getattr(usage, "cache_write_tokens", 0))

    cost, savings = _estimate_cost(model, prompt_tokens, completion_tokens, cache_read, cache_write)

    return LLMUsage(
        model=model,
        operation=operation,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cache_savings_usd=savings,
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
        cache_read=usage.cache_read_tokens,
        cache_write=usage.cache_write_tokens,
        cache_savings_usd=usage.cache_savings_usd,
        channel_id=usage.channel_id,
    )


def get_session_summary() -> dict[str, Any]:
    """Return accumulated usage summary: total tokens, cost, cache savings, and per-operation breakdown."""
    total_tokens = 0
    total_cost = 0.0
    total_cache_read = 0
    total_cache_write = 0
    total_savings = 0.0
    by_operation: dict[str, dict[str, float | int]] = {}

    for u in _usage_history:
        total_tokens += u.total_tokens
        total_cost += u.estimated_cost_usd
        total_cache_read += u.cache_read_tokens
        total_cache_write += u.cache_write_tokens
        total_savings += u.cache_savings_usd

        if u.operation not in by_operation:
            by_operation[u.operation] = {"tokens": 0, "cost_usd": 0.0, "calls": 0, "cache_savings_usd": 0.0}

        by_operation[u.operation]["tokens"] += u.total_tokens
        by_operation[u.operation]["cost_usd"] += u.estimated_cost_usd
        by_operation[u.operation]["calls"] += 1
        by_operation[u.operation]["cache_savings_usd"] += u.cache_savings_usd

    return {
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 8),
        "total_calls": len(_usage_history),
        "cache_read_tokens": total_cache_read,
        "cache_write_tokens": total_cache_write,
        "cache_savings_usd": round(total_savings, 8),
        "by_operation": by_operation,
    }


def reset_usage_history() -> None:
    """Clear accumulated usage history (useful for testing)."""
    _usage_history.clear()
