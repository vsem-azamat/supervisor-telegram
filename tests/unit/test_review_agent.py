"""Tests for the channel post review agent."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.channel.review.agent import (
    _MAX_REVIEW_CONVERSATIONS,
    ReviewConversationRegistry,
    _registry,
    clear_review_conversation,
    create_review_agent,
)

# ---------------------------------------------------------------------------
# Test agent creation
# ---------------------------------------------------------------------------


class TestCreateReviewAgent:
    def test_creates_agent_with_expected_tools(self) -> None:
        """Verify the agent has at least the expected set of tools registered.

        Uses private _function_toolset.tools because PydanticAI does not expose
        a public API for tool introspection. Asserting >= to avoid brittleness
        when new tools are added.
        """
        agent = create_review_agent()
        tool_names = set(agent._function_toolset.tools.keys())
        expected = {
            "get_current_post",
            "web_search",
            "update_post",
            "list_images",
            "use_candidate",
            "add_image_url",
            "find_and_add_image",
            "remove_image",
            "reorder_images",
            "clear_images",
        }
        assert expected <= tool_names, f"Missing tools: {expected - tool_names}"
        assert len(tool_names) >= len(expected)


# ---------------------------------------------------------------------------
# Test conversation memory
# ---------------------------------------------------------------------------


class TestReviewConversationMemory:
    def setup_method(self) -> None:
        """Clear the singleton registry before each test."""
        _registry._conversations.clear()
        _registry._last_access.clear()
        _registry._message_to_post.clear()
        _registry._post_locks.clear()

    def test_clear_conversation_removes_entry(self) -> None:
        """clear_review_conversation removes the entry for a post_id."""
        _registry.set_history(42, [MagicMock()])
        clear_review_conversation(42)
        assert _registry.get_history(42) is None

    def test_clear_nonexistent_is_noop(self) -> None:
        """Clearing a nonexistent post_id doesn't raise."""
        clear_review_conversation(99999)  # Should not raise

    def test_eviction_removes_old_entries(self) -> None:
        """Old conversations (beyond TTL) are evicted."""
        registry = ReviewConversationRegistry(max_conversations=100, ttl=10_000)
        now = time.monotonic()
        registry._conversations[1] = [MagicMock()]
        registry._last_access[1] = now - 20_000
        registry._conversations[2] = [MagicMock()]
        registry._last_access[2] = now

        registry.evict_stale()

        assert registry.get_history(1) is None
        assert registry.get_history(2) is not None

    def test_eviction_lru_when_over_max(self) -> None:
        """When over max conversations, LRU entries are dropped."""
        registry = ReviewConversationRegistry()
        now = time.monotonic()
        overflow = _MAX_REVIEW_CONVERSATIONS + 10
        for i in range(overflow):
            registry._conversations[i] = [MagicMock()]
            registry._last_access[i] = now - (overflow - i)

        registry.evict_stale()

        assert len(registry._conversations) <= _MAX_REVIEW_CONVERSATIONS


# ---------------------------------------------------------------------------
# build_schedule_picker_keyboard
# ---------------------------------------------------------------------------


class TestBuildSchedulePickerKeyboard:
    def test_builds_keyboard_with_slots(self) -> None:
        from datetime import datetime

        from app.channel.review import build_schedule_picker_keyboard

        slots = [
            datetime(2026, 3, 8, 9, 0, 0),
            datetime(2026, 3, 8, 15, 0, 0),
        ]
        kb = build_schedule_picker_keyboard(42, slots)
        # 2 slot rows + 1 action row (publish now + back)
        assert len(kb.inline_keyboard) == 3
        assert "\U0001f4c5" in kb.inline_keyboard[0][0].text
        assert (kb.inline_keyboard[0][0].callback_data or "").startswith("rvsp:42:")
        assert (kb.inline_keyboard[2][0].callback_data or "").startswith("rvpub:42")

    def test_limits_to_5_slots(self) -> None:
        from datetime import datetime

        from app.channel.review import build_schedule_picker_keyboard

        slots = [datetime(2026, 3, 8, h, 0, 0) for h in range(8)]
        kb = build_schedule_picker_keyboard(1, slots)
        # 5 slot rows + 1 action row
        assert len(kb.inline_keyboard) == 6
