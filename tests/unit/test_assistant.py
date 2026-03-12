"""Behavioral unit tests for the assistant bot and markdown conversion."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401
from app.assistant.bot import _evict_conversations
from app.core.markdown import md_to_entities, md_to_entities_chunked

# ---------------------------------------------------------------------------
# 1. Markdown -> entities converter tests
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
    @pytest.fixture(autouse=True)
    def _clean_conversations(self):
        """Clear module-level conversation state before and after each test."""
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()
        yield
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
        """Verify the agent registers at least 30 tools.

        Uses private _function_toolset.tools because PydanticAI does not expose
        a public API for tool introspection. Uses >= to avoid brittleness when
        new tools are added.
        """
        from app.assistant.agent import create_assistant_agent

        agent = create_assistant_agent()
        tool_count = len(agent._function_toolset.tools)
        assert tool_count >= 30, f"Expected >= 30 tools, got {tool_count}: {list(agent._function_toolset.tools.keys())}"


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
    @pytest.fixture(autouse=True)
    def _clean_conversations(self):
        """Guarantee cleanup of module-level state."""
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()
        yield
        bot._conversations.clear()
        bot._conversation_last_access.clear()

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

    async def test_returns_timeout_message_on_timeout(self) -> None:
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

    async def test_saves_conversation_history(self) -> None:
        from app.assistant import bot

        saved_agent = bot._agent
        saved_deps = bot._deps

        mock_result = MagicMock()
        mock_result.output = "response text"
        mock_result.all_messages.return_value = [MagicMock(), MagicMock()]
        mock_result.usage.return_value = None  # Skip cost tracking

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


# ---------------------------------------------------------------------------
# 7. _chat_stream() tests
# ---------------------------------------------------------------------------


class TestChatStream:
    @pytest.fixture(autouse=True)
    def _clean_conversations(self):
        """Guarantee cleanup of module-level state."""
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()
        yield
        bot._conversations.clear()
        bot._conversation_last_access.clear()

    async def test_returns_error_when_agent_not_initialized(self) -> None:
        from app.assistant import bot

        saved_agent, saved_deps = bot._agent, bot._deps
        bot._agent = None
        bot._deps = None

        try:
            text, draft_id = await bot._chat_stream(MagicMock(), 123, 456, "hello")
            assert text == "Агент не инициализирован."
            assert draft_id == 0
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps

    async def test_returns_timeout_message_on_timeout(self) -> None:
        from app.assistant import bot

        saved_agent, saved_deps = bot._agent, bot._deps
        saved_timeout = bot._AGENT_TIMEOUT_SECONDS

        # Mock agent with a stream that hangs
        mock_stream_result = MagicMock()

        async def slow_stream(*_args, **_kwargs):
            await asyncio.sleep(999)
            yield "text"  # pragma: no cover

        mock_stream_result.stream_text = slow_stream
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_result)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=mock_stream_ctx)

        bot._agent = mock_agent
        bot._deps = MagicMock()
        bot._AGENT_TIMEOUT_SECONDS = 0.01  # type: ignore[assignment]

        try:
            text, draft_id = await bot._chat_stream(MagicMock(), 123, 456, "hello")
            assert "Превышено время ожидания" in text
            assert draft_id > 0  # draft_id is assigned before timeout
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps
            bot._AGENT_TIMEOUT_SECONDS = saved_timeout

    async def test_draft_throttling(self) -> None:
        """Drafts should only be sent when enough chars accumulated and enough time passed."""
        from app.assistant import bot

        saved_agent, saved_deps = bot._agent, bot._deps

        draft_calls: list[str] = []

        async def fake_send_draft(_bot, _chat_id, _draft_id, text, **_kw):
            draft_calls.append(text)

        # Mock streaming that yields progressively
        chunks = ["Hi", "Hi, this is a longer response that keeps growing with more content"]

        async def fake_stream_text(debounce_by=0):
            for chunk in chunks:
                yield chunk

        mock_stream_result = MagicMock()
        mock_stream_result.stream_text = fake_stream_text
        mock_stream_result.get_output = AsyncMock(return_value="final output")
        mock_stream_result.all_messages.return_value = [MagicMock()]
        mock_stream_result.usage.return_value = None

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_result)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=mock_stream_ctx)

        bot._agent = mock_agent
        bot._deps = MagicMock()

        try:
            with patch("app.assistant.bot._send_draft", side_effect=fake_send_draft):
                with patch("app.assistant.bot.extract_usage_from_pydanticai_result", return_value=None):
                    text, draft_id = await bot._chat_stream(MagicMock(), 123, 456, "hello")
            assert text == "final output"
            # First chunk "Hi" is only 2 chars — below _DRAFT_MIN_CHARS (20), should NOT be sent as draft
            # Second chunk is long enough — should be sent
            # Final draft without cursor should also be sent
            assert len(draft_calls) >= 1
            # No draft should contain just "Hi" (too short)
            assert not any(d.strip() == "Hi" for d in draft_calls)
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps


# ---------------------------------------------------------------------------
# 8. Conversation lock concurrency test
# ---------------------------------------------------------------------------


class TestConversationLock:
    @pytest.fixture(autouse=True)
    def _clean_conversations(self):
        """Guarantee cleanup of module-level state."""
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()
        yield
        bot._conversations.clear()
        bot._conversation_last_access.clear()

    async def test_concurrent_access_doesnt_lose_data(self) -> None:
        """Two concurrent _chat calls for different users should not corrupt state."""
        from app.assistant import bot

        saved_agent, saved_deps = bot._agent, bot._deps

        call_count = 0

        async def fake_run(msg, deps=None, message_history=None):
            nonlocal call_count
            call_count += 1
            # Simulate some async work
            await asyncio.sleep(0.01)
            mock_result = MagicMock()
            mock_result.output = f"response_{call_count}"
            mock_result.all_messages.return_value = [MagicMock()]
            mock_result.usage.return_value = None
            return mock_result

        mock_agent = MagicMock()
        mock_agent.run = fake_run
        bot._agent = mock_agent
        bot._deps = MagicMock()

        try:
            with patch("app.assistant.bot.extract_usage_from_pydanticai_result", return_value=None):
                results = await asyncio.gather(
                    bot._chat(100, "hello"),
                    bot._chat(200, "world"),
                )
            # Both users should have conversation history
            assert 100 in bot._conversations
            assert 200 in bot._conversations
            assert len(results) == 2
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps


# ---------------------------------------------------------------------------
# 9. md_to_entities_chunked boundary tests
# ---------------------------------------------------------------------------


class TestMdToEntitiesChunkedBoundary:
    def test_exactly_at_max_len_is_single_chunk(self) -> None:
        text = "a" * 4096
        chunks = md_to_entities_chunked(text)
        assert len(chunks) == 1
        assert len(chunks[0][0]) <= 4096

    def test_one_over_max_len_splits(self) -> None:
        text = "a" * 4097
        chunks = md_to_entities_chunked(text)
        assert len(chunks) >= 2
        for chunk_text, _ in chunks:
            assert len(chunk_text) <= 4096

    def test_custom_max_len_respected(self) -> None:
        text = "word " * 100  # 500 chars
        chunks = md_to_entities_chunked(text, max_len=100)
        assert len(chunks) >= 5
        for chunk_text, _ in chunks:
            assert len(chunk_text) <= 100


# ---------------------------------------------------------------------------
# 10. Cost tracker timestamp test
# ---------------------------------------------------------------------------


class TestCostTrackerTimestamp:
    def test_usage_created_at_is_utc(self) -> None:
        from app.agent.channel.cost_tracker import LLMUsage

        usage = LLMUsage(
            model="test",
            operation="test",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=0.001,
        )
        # Should use utc_now(), not datetime.now() — verify it has no timezone info (naive UTC)
        assert usage.created_at.tzinfo is None
        # Should be recent (within last 5 seconds)
        from datetime import UTC, datetime

        now_utc = datetime.now(UTC).replace(tzinfo=None)
        assert abs((now_utc - usage.created_at).total_seconds()) < 5


# ---------------------------------------------------------------------------
# 11. SuperAdminOnly middleware and handler tests
# ---------------------------------------------------------------------------


class TestSuperAdminMiddleware:
    """Test that non-admin users are rejected by _SuperAdminOnlyMiddleware."""

    @staticmethod
    def _make_message_mock(user_id: int) -> MagicMock:
        """Create a MagicMock that passes isinstance(event, Message) check."""
        from aiogram.types import Message

        mock = MagicMock(spec=Message)
        mock.from_user = MagicMock()
        mock.from_user.id = user_id
        mock.answer = AsyncMock()
        return mock

    async def test_handle_message_non_admin_rejected(self) -> None:
        """Non-admin user should receive a rejection message from the middleware."""
        from app.assistant.bot import _SuperAdminOnlyMiddleware

        middleware = _SuperAdminOnlyMiddleware()
        msg = self._make_message_mock(user_id=999999)
        mock_handler = AsyncMock()

        from app.assistant import bot

        saved_admins = bot._super_admins
        bot._super_admins = {111111}

        try:
            result = await middleware(mock_handler, msg, {})
        finally:
            bot._super_admins = saved_admins

        assert result is None
        msg.answer.assert_awaited_once_with("Этот бот доступен только для администраторов.")
        mock_handler.assert_not_called()

    async def test_handle_message_admin_allowed(self) -> None:
        """Admin user should pass through the middleware to the handler."""
        from app.assistant.bot import _SuperAdminOnlyMiddleware

        middleware = _SuperAdminOnlyMiddleware()
        msg = self._make_message_mock(user_id=111111)
        mock_handler = AsyncMock(return_value="handler_result")

        from app.assistant import bot

        saved_admins = bot._super_admins
        bot._super_admins = {111111}

        try:
            result = await middleware(mock_handler, msg, {})
        finally:
            bot._super_admins = saved_admins

        assert result == "handler_result"
        mock_handler.assert_awaited_once()


class TestCmdStart:
    async def test_cmd_start_responds(self) -> None:
        """The /start command should respond with the introduction message."""
        from app.assistant.bot import cmd_start

        mock_message = MagicMock()
        mock_message.answer = AsyncMock()

        await cmd_start(mock_message)

        mock_message.answer.assert_awaited_once()
        response_text = mock_message.answer.call_args[0][0]
        assert "Konnekt Assistant" in response_text
        assert "Управлять каналами" in response_text


class TestHandleMessageParseMode:
    @pytest.fixture(autouse=True)
    def _clean_conversations(self):
        """Guarantee cleanup of module-level state."""
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()
        yield
        bot._conversations.clear()
        bot._conversation_last_access.clear()

    async def test_handle_message_uses_parse_mode_none(self) -> None:
        """handle_message must pass parse_mode=None when sending entities."""
        from app.assistant import bot
        from app.assistant.bot import handle_message

        saved_agent, saved_deps = bot._agent, bot._deps

        # Mock agent that returns a simple response
        mock_result = MagicMock()
        mock_result.stream_text = None
        mock_result.get_output = AsyncMock(return_value="**bold response**")
        mock_result.all_messages.return_value = [MagicMock()]
        mock_result.usage.return_value = None

        mock_stream_result = MagicMock()

        async def fake_stream_text(debounce_by=0):
            yield "**bold response**"

        mock_stream_result.stream_text = fake_stream_text
        mock_stream_result.get_output = AsyncMock(return_value="**bold response**")
        mock_stream_result.all_messages.return_value = [MagicMock()]
        mock_stream_result.usage.return_value = None

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_result)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_agent = MagicMock()
        mock_agent.run_stream = MagicMock(return_value=mock_stream_ctx)

        bot._agent = mock_agent
        bot._deps = MagicMock()

        mock_message = MagicMock()
        mock_message.from_user = MagicMock()
        mock_message.from_user.id = 42
        mock_message.text = "hello"
        mock_message.chat = MagicMock()
        mock_message.chat.id = 42
        mock_message.bot = MagicMock()
        mock_message.answer = AsyncMock()

        try:
            with patch("app.assistant.bot._send_draft", new_callable=AsyncMock):
                with patch("app.assistant.bot.extract_usage_from_pydanticai_result", return_value=None):
                    await handle_message(mock_message)
        finally:
            bot._agent = saved_agent
            bot._deps = saved_deps

        # Verify parse_mode=None was passed in the answer call
        mock_message.answer.assert_awaited()
        for call in mock_message.answer.call_args_list:
            kwargs = call[1] if call[1] else {}
            assert kwargs.get("parse_mode") is None, "parse_mode must be None when using entities"
