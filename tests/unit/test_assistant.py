"""Behavioral unit tests for the assistant bot module."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio  # noqa: F401
from app.assistant.bot import _evict_conversations, _md_to_html, _split_html_safe

# ---------------------------------------------------------------------------
# 1. MD -> HTML converter tests
# ---------------------------------------------------------------------------


class TestMdToHtml:
    def test_bold(self) -> None:
        assert _md_to_html("**text**") == "<b>text</b>"

    def test_italic_double_underscore(self) -> None:
        assert _md_to_html("__text__") == "<i>text</i>"

    def test_italic(self) -> None:
        assert _md_to_html("*text*") == "<i>text</i>"

    def test_inline_code(self) -> None:
        assert _md_to_html("`code`") == "<code>code</code>"

    def test_code_block(self) -> None:
        result = _md_to_html("```python\ncode\n```")
        assert "<pre>" in result
        assert "code" in result

    def test_code_block_no_language(self) -> None:
        result = _md_to_html("```\ncode\n```")
        assert "<pre>" in result
        assert "code" in result

    def test_header(self) -> None:
        assert _md_to_html("### Title") == "<b>Title</b>"

    def test_header_h1(self) -> None:
        assert _md_to_html("# Title") == "<b>Title</b>"

    def test_header_h2(self) -> None:
        assert _md_to_html("## Title") == "<b>Title</b>"

    def test_mixed_bold_and_italic(self) -> None:
        result = _md_to_html("**bold** and *italic*")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result

    def test_html_entities_escaped(self) -> None:
        assert _md_to_html("I <3 cats & dogs") == "I &lt;3 cats &amp; dogs"

    def test_link_converted(self) -> None:
        result = _md_to_html("[click](https://example.com)")
        assert result == '<a href="https://example.com">click</a>'

    def test_plain_text_unchanged(self) -> None:
        text = "Hello, this is plain text."
        assert _md_to_html(text) == text

    def test_nested_bold_italic_no_crash(self) -> None:
        # Known limitation -- just check it doesn't crash
        result = _md_to_html("**bold *italic* bold**")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# 2. HTML-safe splitter tests
# ---------------------------------------------------------------------------


class TestSplitHtmlSafe:
    def test_short_text_single_chunk(self) -> None:
        text = "Hello world"
        assert _split_html_safe(text) == [text]

    def test_empty_text(self) -> None:
        assert _split_html_safe("") == [""]

    def test_exactly_4096_characters(self) -> None:
        text = "a" * 4096
        assert _split_html_safe(text) == [text]

    def test_long_text_splits_on_line_boundaries(self) -> None:
        # Create text with many lines that exceed 4096 total
        lines = [f"Line {i}: " + "x" * 80 for i in range(100)]
        text = "\n".join(lines)
        chunks = _split_html_safe(text)
        assert len(chunks) > 1
        # All chunks should be within the limit
        for chunk in chunks:
            assert len(chunk) <= 4096
        # Reassembling should give back the original content (by characters)
        reassembled = "\n".join(chunks)
        assert reassembled == text

    def test_very_long_single_line_hard_split(self) -> None:
        text = "x" * 10000
        chunks = _split_html_safe(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 4096
        # Reassembled content should match
        assert "".join(chunks) == text

    def test_custom_max_len(self) -> None:
        text = "line1\nline2\nline3"
        chunks = _split_html_safe(text, max_len=10)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= 10


# ---------------------------------------------------------------------------
# 3. Conversation eviction tests
# ---------------------------------------------------------------------------


class TestEvictConversations:
    def setup_method(self) -> None:
        """Clear module-level conversation state before each test."""
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    def test_old_conversations_evicted(self) -> None:
        from app.assistant import bot

        now = time.monotonic()
        # Add a conversation that's 2 hours old
        bot._conversations[111] = [MagicMock()]
        bot._conversation_last_access[111] = now - 7200  # 2 hours ago

        # Add a recent conversation
        bot._conversations[222] = [MagicMock()]
        bot._conversation_last_access[222] = now

        _evict_conversations()

        assert 111 not in bot._conversations
        assert 111 not in bot._conversation_last_access
        assert 222 in bot._conversations
        assert 222 in bot._conversation_last_access

    def test_recent_conversations_kept(self) -> None:
        from app.assistant import bot

        now = time.monotonic()
        bot._conversations[333] = [MagicMock()]
        bot._conversation_last_access[333] = now - 60  # 1 minute ago

        _evict_conversations()

        assert 333 in bot._conversations

    def test_lru_eviction_when_over_max_users(self) -> None:
        from app.assistant import bot

        now = time.monotonic()
        # Fill with 55 users (above _MAX_USERS=50), all recent
        for uid in range(55):
            bot._conversations[uid] = [MagicMock()]
            bot._conversation_last_access[uid] = now - (55 - uid)  # oldest first

        _evict_conversations()

        # Should have at most 50 users remaining
        assert len(bot._conversations) <= 50
        assert len(bot._conversation_last_access) <= 50

        # The 5 oldest (uid 0-4) should have been evicted
        for uid in range(5):
            assert uid not in bot._conversations

        # The newest should still be there
        for uid in range(50, 55):
            assert uid in bot._conversations


# ---------------------------------------------------------------------------
# 4. Agent creation test
# ---------------------------------------------------------------------------


class TestCreateAssistantAgent:
    def test_create_agent_returns_agent(self) -> None:
        from app.assistant.agent import create_assistant_agent
        from pydantic_ai import Agent

        agent = create_assistant_agent()
        assert isinstance(agent, Agent)

    def test_agent_has_expected_tool_count(self) -> None:
        from app.assistant.agent import create_assistant_agent

        agent = create_assistant_agent()
        # Count tools registered on the agent
        tool_count = len(agent._function_toolset.tools)
        # 24 tools defined in agent.py
        assert tool_count == 24, f"Expected 24 tools, got {tool_count}: {list(agent._function_toolset.tools.keys())}"


# ---------------------------------------------------------------------------
# 5. Schedule time regex validation
# ---------------------------------------------------------------------------


class TestScheduleTimeRegex:
    def setup_method(self) -> None:
        from app.assistant.agent import _SCHEDULE_TIME_RE

        self.pattern = _SCHEDULE_TIME_RE

    def test_valid_times(self) -> None:
        valid = ["00:00", "09:00", "12:30", "23:59", "15:45"]
        for t in valid:
            assert self.pattern.match(t), f"{t} should be valid"

    def test_invalid_times(self) -> None:
        invalid = ["25:00", "99:99", "abc", "24:00", "12:60", "9:00", "1:1", ""]
        for t in invalid:
            assert not self.pattern.match(t), f"{t} should be invalid"


# ---------------------------------------------------------------------------
# 6. _chat() function tests
# ---------------------------------------------------------------------------


class TestChat:
    @pytest.mark.asyncio
    async def test_returns_error_when_agent_not_initialized(self) -> None:
        from app.assistant import bot

        # Save and clear module state
        saved_agent = bot._agent
        saved_deps = bot._deps
        bot._agent = None
        bot._deps = None

        try:
            result = await bot._chat(123, "hello")
            assert result == "Агент не инициализирован."
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps

    @pytest.mark.asyncio
    async def test_returns_timeout_message_on_timeout(self) -> None:
        import asyncio

        from app.assistant import bot

        saved_agent = bot._agent
        saved_deps = bot._deps

        mock_agent = MagicMock()

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(999)

        mock_agent.run = slow_run
        mock_deps = MagicMock()

        bot._agent = mock_agent
        bot._deps = mock_deps

        # Override timeout to be very short
        saved_timeout = bot._AGENT_TIMEOUT_SECONDS
        bot._AGENT_TIMEOUT_SECONDS = 0.01  # type: ignore[assignment]

        try:
            result = await bot._chat(123, "hello")
            assert "Превышено время ожидания" in result
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps
            bot._AGENT_TIMEOUT_SECONDS = saved_timeout

    @pytest.mark.asyncio
    async def test_saves_conversation_history(self) -> None:
        from app.assistant import bot

        saved_agent = bot._agent
        saved_deps = bot._deps
        bot._conversations.clear()
        bot._conversation_last_access.clear()

        mock_result = MagicMock()
        mock_result.output = "response text"
        mock_result.all_messages.return_value = [MagicMock(), MagicMock()]

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        bot._agent = mock_agent
        bot._deps = MagicMock()

        try:
            result = await bot._chat(42, "hello")
            assert result == "response text"
            assert 42 in bot._conversations
            assert 42 in bot._conversation_last_access
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps
            bot._conversations.clear()
            bot._conversation_last_access.clear()
