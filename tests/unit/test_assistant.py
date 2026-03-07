"""Behavioral unit tests for the assistant bot and markdown conversion."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio  # noqa: F401
from app.assistant.bot import _evict_conversations
from app.core.markdown import md_to_entities, md_to_entities_chunked

# ---------------------------------------------------------------------------
# 1. Markdown → entities converter tests
# ---------------------------------------------------------------------------


class TestMdToEntities:
    def test_bold(self) -> None:
        text, entities = md_to_entities("**text**")
        assert text == "text"
        assert len(entities) == 1
        assert entities[0].type == "bold"

    def test_italic(self) -> None:
        text, entities = md_to_entities("*text*")
        assert text == "text"
        assert len(entities) == 1
        assert entities[0].type == "italic"

    def test_inline_code(self) -> None:
        text, entities = md_to_entities("`code`")
        assert text == "code"
        assert len(entities) == 1
        assert entities[0].type == "code"

    def test_code_block(self) -> None:
        text, entities = md_to_entities("```python\nprint(1)\n```")
        assert "print(1)" in text
        assert any(e.type == "pre" for e in entities)

    def test_link(self) -> None:
        text, entities = md_to_entities("[click](https://example.com)")
        assert text == "click"
        assert len(entities) == 1
        assert entities[0].type == "text_link"
        assert entities[0].url == "https://example.com"

    def test_mixed_formatting(self) -> None:
        text, entities = md_to_entities("**bold** and *italic* and `code`")
        assert "bold" in text
        assert "italic" in text
        assert "code" in text
        types = {e.type for e in entities}
        assert "bold" in types
        assert "italic" in types
        assert "code" in types

    def test_plain_text_no_entities(self) -> None:
        text, entities = md_to_entities("Hello, this is plain text.")
        assert text == "Hello, this is plain text."
        assert entities == []

    def test_html_chars_safe(self) -> None:
        text, entities = md_to_entities("I <3 cats & dogs")
        assert "<3" in text  # Literal, not HTML
        assert "&" in text  # Literal, not &amp;

    def test_channel_post_format(self) -> None:
        md = "💰 **Реальные зарплаты растут**\n\nТекст поста.\n\n[Подробнее](https://example.com)"
        text, entities = md_to_entities(md)
        assert "Реальные зарплаты растут" in text
        assert "Подробнее" in text
        assert any(e.type == "bold" for e in entities)
        assert any(e.type == "text_link" for e in entities)


# ---------------------------------------------------------------------------
# 2. Chunked conversion tests
# ---------------------------------------------------------------------------


class TestMdToEntitiesChunked:
    def test_short_text_single_chunk(self) -> None:
        chunks = md_to_entities_chunked("Hello **world**")
        assert len(chunks) == 1
        text, entities = chunks[0]
        assert "world" in text
        assert any(e.type == "bold" for e in entities)

    def test_empty_text(self) -> None:
        chunks = md_to_entities_chunked("")
        assert len(chunks) == 1
        assert chunks[0][0] == ""

    def test_respects_max_len(self) -> None:
        # Generate text longer than max_len
        long_md = "\n\n".join(f"Line {i}: " + "x" * 80 for i in range(100))
        chunks = md_to_entities_chunked(long_md, max_len=500)
        assert len(chunks) > 1
        for text, _ in chunks:
            assert len(text) <= 500


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
        bot._conversations[111] = [MagicMock()]
        bot._conversation_last_access[111] = now - 7200  # 2 hours ago

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
        bot._conversation_last_access[333] = now - 60

        _evict_conversations()

        assert 333 in bot._conversations

    def test_lru_eviction_when_over_max_users(self) -> None:
        from app.assistant import bot

        now = time.monotonic()
        for uid in range(55):
            bot._conversations[uid] = [MagicMock()]
            bot._conversation_last_access[uid] = now - (55 - uid)

        _evict_conversations()

        assert len(bot._conversations) <= 50
        assert len(bot._conversation_last_access) <= 50

        for uid in range(5):
            assert uid not in bot._conversations

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
        tool_count = len(agent._function_toolset.tools)
        assert tool_count == 32, f"Expected 32 tools, got {tool_count}: {list(agent._function_toolset.tools.keys())}"


# ---------------------------------------------------------------------------
# 5. Schedule time regex validation
# ---------------------------------------------------------------------------


class TestScheduleTimeRegex:
    def setup_method(self) -> None:
        from app.assistant.tools.channel import _SCHEDULE_TIME_RE

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
