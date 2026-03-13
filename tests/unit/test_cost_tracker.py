"""Tests for app.agent.channel.cost_tracker — LLMUsage timestamp behavior."""

from __future__ import annotations

from datetime import datetime

from app.agent.channel.cost_tracker import LLMUsage
from app.core.time import utc_now


class TestCostTrackerTimestamp:
    def test_usage_created_at_is_naive_utc(self) -> None:
        before = utc_now()
        usage = LLMUsage(
            model="test",
            operation="test",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=0.001,
        )
        after = utc_now()

        assert isinstance(usage.created_at, datetime)
        assert usage.created_at.tzinfo is None  # naive UTC, not aware
        assert before <= usage.created_at <= after
