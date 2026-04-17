"""Tests for the channel post review agent."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.channel.review.agent import (
    _MAX_REVIEW_CONVERSATIONS,
    _evict_review_conversations,
    _review_conversations,
    _review_last_access,
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
            "find_new_images",
            "replace_images",
            "remove_images",
        }
        assert expected <= tool_names, f"Missing tools: {expected - tool_names}"
        assert len(tool_names) >= len(expected)


# ---------------------------------------------------------------------------
# Test conversation memory
# ---------------------------------------------------------------------------


class TestReviewConversationMemory:
    def setup_method(self) -> None:
        """Clear conversation state before each test."""
        _review_conversations.clear()
        _review_last_access.clear()

    def test_clear_conversation_removes_entry(self) -> None:
        """clear_review_conversation removes the entry for a post_id."""
        _review_conversations[42] = [MagicMock()]
        _review_last_access[42] = time.monotonic()
        clear_review_conversation(42)
        assert 42 not in _review_conversations
        assert 42 not in _review_last_access

    def test_clear_nonexistent_is_noop(self) -> None:
        """Clearing a nonexistent post_id doesn't raise."""
        clear_review_conversation(99999)  # Should not raise

    def test_eviction_removes_old_entries(self) -> None:
        """Old conversations (beyond TTL) are evicted."""
        now = time.monotonic()
        # Old entry — way past TTL
        _review_conversations[1] = [MagicMock()]
        _review_last_access[1] = now - 20000
        # Fresh entry
        _review_conversations[2] = [MagicMock()]
        _review_last_access[2] = now

        _evict_review_conversations()

        assert 1 not in _review_conversations
        assert 2 in _review_conversations

    def test_eviction_lru_when_over_max(self) -> None:
        """When over max conversations, LRU entries are dropped."""
        now = time.monotonic()
        overflow = _MAX_REVIEW_CONVERSATIONS + 10
        for i in range(overflow):
            _review_conversations[i] = [MagicMock()]
            _review_last_access[i] = now - (overflow - i)

        _evict_review_conversations()

        assert len(_review_conversations) <= _MAX_REVIEW_CONVERSATIONS


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
