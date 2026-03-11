"""Tests for the channel post review agent."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from app.agent.channel.review_agent import (
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
        """Verify the agent has the right tools registered."""
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
        assert expected == tool_names, f"Expected {expected}, got {tool_names}"

    def test_agent_is_pydantic_agent(self) -> None:
        """Verify it returns a pydantic_ai.Agent instance."""
        from pydantic_ai import Agent

        agent = create_review_agent()
        assert isinstance(agent, Agent)


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
# Test enforce_footer_and_length integration
# ---------------------------------------------------------------------------


class TestEnforceFooterAndLength:
    def test_appends_footer_when_missing(self) -> None:
        from app.agent.channel.generator import enforce_footer_and_length

        result = enforce_footer_and_length("Hello world", "——\nFooter")
        assert result.endswith("——\nFooter")

    def test_preserves_footer_when_present(self) -> None:
        from app.agent.channel.generator import enforce_footer_and_length

        text = "Hello world\n\n——\nFooter"
        result = enforce_footer_and_length(text, "——\nFooter")
        assert result.count("——\nFooter") == 1

    def test_truncates_to_max_length(self) -> None:
        from app.agent.channel.generator import enforce_footer_and_length

        long_text = "A" * 1000
        footer = "——\nFooter"
        result = enforce_footer_and_length(long_text, footer, max_length=200)
        assert len(result) <= 200
        assert result.endswith(footer)

    def test_uses_default_footer_when_empty(self) -> None:
        from app.agent.channel.generator import DEFAULT_FOOTER, enforce_footer_and_length

        result = enforce_footer_and_length("Hello", "")
        assert DEFAULT_FOOTER in result


# ---------------------------------------------------------------------------
# Test Channel.footer property
# ---------------------------------------------------------------------------


class TestChannelFooter:
    def test_footer_with_template(self) -> None:
        from app.infrastructure.db.models import Channel

        ch = Channel(telegram_id="@test", name="Test", footer_template="Custom footer")
        assert ch.footer == "Custom footer"

    def test_footer_without_template_uses_username(self) -> None:
        from app.infrastructure.db.models import Channel

        ch = Channel(telegram_id="@test", name="MyChannel", username="mychan")
        assert "MyChannel" in ch.footer
        assert "@mychan" in ch.footer

    def test_footer_without_template_or_username(self) -> None:
        from app.infrastructure.db.models import Channel

        ch = Channel(telegram_id="@testchan", name="TestChan")
        assert "TestChan" in ch.footer
        assert "@testchan" in ch.footer

    def test_footer_numeric_id_no_at_mention(self) -> None:
        from app.infrastructure.db.models import Channel

        ch = Channel(telegram_id="-1001234567890", name="NumChannel")
        assert "NumChannel" in ch.footer
        assert "@" not in ch.footer

    def test_footer_username_with_at_prefix_no_double_at(self) -> None:
        """Regression: username stored with @ prefix must not produce @@username."""
        from app.infrastructure.db.models import Channel

        ch = Channel(telegram_id="@test_chan", name="TestChan", username="@test_chan")
        assert "@@" not in ch.footer
        assert "@test_chan" in ch.footer

    def test_footer_telegram_id_with_at_prefix(self) -> None:
        """Regression: telegram_id starting with @ must be stripped when used as fallback."""
        from app.infrastructure.db.models import Channel

        ch = Channel(telegram_id="@mychannel", name="MyChan")
        assert "@@" not in ch.footer
        assert "@mychannel" in ch.footer
