"""Integration tests for assistant bot conversation persistence.

Verifies that multi-turn conversations with tool calls maintain context
properly — the core issue where the model "forgets" what was discussed
and generates posts about wrong topics.

Uses PydanticAI's FunctionModel to control LLM responses precisely.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.assistant.agent import AssistantDeps
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deps() -> AssistantDeps:
    """Create mock deps for tests."""
    return AssistantDeps(
        session_maker=AsyncMock(),
        main_bot=MagicMock(),
        channel_orchestrator=None,
        telethon=None,
    )


def _count_user_prompts(messages: list[ModelMessage]) -> int:
    """Count how many user prompt parts exist in the message history."""
    count = 0
    for msg in messages:
        if isinstance(msg, ModelRequest):
            count += sum(1 for p in msg.parts if isinstance(p, UserPromptPart))
    return count


def _count_tool_returns(messages: list[ModelMessage]) -> int:
    """Count how many tool return parts exist in the message history."""
    count = 0
    for msg in messages:
        if isinstance(msg, ModelRequest):
            count += sum(1 for p in msg.parts if isinstance(p, ToolReturnPart))
    return count


def _find_text_in_history(messages: list[ModelMessage], needle: str) -> bool:
    """Check if a string appears anywhere in the message history."""
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for req_part in msg.parts:
                if isinstance(req_part, UserPromptPart) and needle in str(req_part.content):
                    return True
                if isinstance(req_part, ToolReturnPart) and needle in str(req_part.content):
                    return True
        elif isinstance(msg, ModelResponse):
            for resp_part in msg.parts:
                if isinstance(resp_part, TextPart) and needle in resp_part.content:
                    return True
    return False


# ---------------------------------------------------------------------------
# Tests: Conversation history persistence across turns
# ---------------------------------------------------------------------------


class TestConversationPersistence:
    """Test that conversation history is maintained across multiple _chat() turns."""

    def setup_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    def teardown_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    @pytest.mark.asyncio
    async def test_history_grows_across_turns(self) -> None:
        """Each turn should add messages to the conversation history."""
        from app.assistant import bot

        turn_counter = 0

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal turn_counter
            turn_counter += 1
            return ModelResponse(parts=[TextPart(content=f"Response #{turn_counter}")])

        mock_agent = Agent(FunctionModel(model_fn), output_type=str)
        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = mock_agent  # type: ignore[assignment]
        bot._deps = mock_deps

        try:
            # Turn 1
            r1 = await bot._chat(100, "Hello")
            assert r1 == "Response #1"
            assert 100 in bot._conversations
            msgs_after_1 = len(bot._conversations[100])

            # Turn 2
            r2 = await bot._chat(100, "Follow up question")
            assert r2 == "Response #2"
            msgs_after_2 = len(bot._conversations[100])
            assert msgs_after_2 > msgs_after_1

            # Turn 3
            r3 = await bot._chat(100, "Another question")
            assert r3 == "Response #3"
            msgs_after_3 = len(bot._conversations[100])
            assert msgs_after_3 > msgs_after_2
        finally:
            bot._agent, bot._deps = saved

    @pytest.mark.asyncio
    async def test_previous_messages_visible_to_model(self) -> None:
        """The model should see all previous messages in each turn."""
        from app.assistant import bot

        received_histories: list[int] = []

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            user_count = _count_user_prompts(messages)
            received_histories.append(user_count)
            return ModelResponse(parts=[TextPart(content="ok")])

        mock_agent = Agent(FunctionModel(model_fn), output_type=str)
        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = mock_agent  # type: ignore[assignment]
        bot._deps = mock_deps

        try:
            await bot._chat(200, "Message 1")
            await bot._chat(200, "Message 2")
            await bot._chat(200, "Message 3")

            # Each subsequent turn should see more user messages
            assert received_histories[0] == 1  # First turn: just "Message 1"
            assert received_histories[1] == 2  # Second turn: "Message 1" + "Message 2"
            assert received_histories[2] == 3  # Third turn: all three
        finally:
            bot._agent, bot._deps = saved

    @pytest.mark.asyncio
    async def test_specific_content_preserved_in_history(self) -> None:
        """Specific content from earlier turns must be findable in history."""
        from app.assistant import bot

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="Found: ČVUT bee scales research at FEL")])

        mock_agent = Agent(FunctionModel(model_fn), output_type=str)
        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = mock_agent  # type: ignore[assignment]
        bot._deps = mock_deps

        try:
            # Turn 1: search for something specific
            await bot._chat(300, "Найди новости про ČVUT")

            # Verify the conversation history contains both the user message and response
            history = bot._conversations[300]
            assert _find_text_in_history(history, "ČVUT")
            assert _find_text_in_history(history, "bee scales")

            # Turn 2: reference the earlier content
            await bot._chat(300, "Отправь это на ревью")

            # The full history should still contain the original content
            history = bot._conversations[300]
            assert _find_text_in_history(history, "ČVUT")
            assert _find_text_in_history(history, "bee scales")
            assert _find_text_in_history(history, "ревью")
        finally:
            bot._agent, bot._deps = saved


class TestConversationWithToolCalls:
    """Test that tool call results are preserved in conversation history."""

    def setup_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    def teardown_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    @pytest.mark.asyncio
    async def test_tool_results_in_history(self) -> None:
        """Tool call results should be preserved in conversation history for next turn."""
        from app.assistant import bot

        # Create a simple agent with a mock tool
        call_count = 0

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal call_count
            call_count += 1

            # First call in first turn: call the tool
            if call_count == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="mock_search",
                            args={"query": "CVUT news"},
                            tool_call_id="call_1",
                        )
                    ]
                )
            # Second call (after tool return): respond with text
            if call_count == 2:
                return ModelResponse(parts=[TextPart(content="Found: ČVUT students built smart bee scales at FEL")])
            # Third call (second turn): should see tool results in history
            if call_count == 3:
                # Verify history contains the tool return
                has_tool_return = _count_tool_returns(messages) > 0
                has_cvut = _find_text_in_history(messages, "CVUT news")
                return ModelResponse(
                    parts=[TextPart(content=f"History has tool returns: {has_tool_return}, has CVUT: {has_cvut}")]
                )
            return ModelResponse(parts=[TextPart(content="unexpected call")])

        agent: Agent[AssistantDeps, str] = Agent(
            FunctionModel(model_fn),
            deps_type=AssistantDeps,
            output_type=str,
        )

        @agent.tool_plain
        async def mock_search(query: str) -> str:
            """Search mock."""
            return f"Search results for '{query}': ČVUT FEL students created smart bee hive scales"

        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = agent
        bot._deps = mock_deps

        try:
            # Turn 1: triggers tool call
            r1 = await bot._chat(400, "Search CVUT news")
            assert "bee scales" in r1

            # Verify tool returns are in history
            history = bot._conversations[400]
            assert _count_tool_returns(history) > 0
            assert _find_text_in_history(history, "bee hive scales")

            # Turn 2: model should see tool results from turn 1
            r2 = await bot._chat(400, "Send this to review")
            assert "tool returns: True" in r2
            assert "has CVUT: True" in r2
        finally:
            bot._agent, bot._deps = saved

    @pytest.mark.asyncio
    async def test_multi_tool_calls_preserved(self) -> None:
        """Multiple tool calls across turns should all be preserved."""
        from app.assistant import bot

        call_count = 0

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Turn 1: call tool_a
                return ModelResponse(parts=[ToolCallPart(tool_name="tool_a", args={}, tool_call_id="a1")])
            if call_count == 2:
                return ModelResponse(parts=[TextPart(content="Got result A")])
            if call_count == 3:
                # Turn 2: call tool_b
                return ModelResponse(parts=[ToolCallPart(tool_name="tool_b", args={}, tool_call_id="b1")])
            if call_count == 4:
                return ModelResponse(parts=[TextPart(content="Got result B")])
            if call_count == 5:
                # Turn 3: verify both tool results are in history
                tool_returns = _count_tool_returns(messages)
                has_alpha = _find_text_in_history(messages, "alpha_data")
                has_beta = _find_text_in_history(messages, "beta_data")
                return ModelResponse(
                    parts=[TextPart(content=f"returns={tool_returns}, alpha={has_alpha}, beta={has_beta}")]
                )
            return ModelResponse(parts=[TextPart(content="done")])

        agent: Agent[AssistantDeps, str] = Agent(
            FunctionModel(model_fn),
            deps_type=AssistantDeps,
            output_type=str,
        )

        @agent.tool_plain
        async def tool_a() -> str:
            """Tool A."""
            return "alpha_data_from_tool_a"

        @agent.tool_plain
        async def tool_b() -> str:
            """Tool B."""
            return "beta_data_from_tool_b"

        mock_deps = _make_deps()
        saved = bot._agent, bot._deps
        bot._agent = agent
        bot._deps = mock_deps

        try:
            await bot._chat(500, "Call A")
            await bot._chat(500, "Call B")
            r3 = await bot._chat(500, "Check history")

            assert "alpha=True" in r3
            assert "beta=True" in r3
            # Should have at least 2 tool returns
            assert "returns=2" in r3 or "returns=3" in r3 or "returns=4" in r3
        finally:
            bot._agent, bot._deps = saved


class TestConversationIsolation:
    """Test that conversations between different users are isolated."""

    def setup_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    def teardown_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    @pytest.mark.asyncio
    async def test_users_have_separate_histories(self) -> None:
        """Different users should not see each other's conversation."""
        from app.assistant import bot

        received_messages: dict[str, int] = {}

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            user_count = _count_user_prompts(messages)
            # The last user message tells us which user this is
            last_user = ""
            for msg in reversed(messages):
                if isinstance(msg, ModelRequest):
                    for req_part in msg.parts:
                        if isinstance(req_part, UserPromptPart):
                            last_user = str(req_part.content)
                            break
                if last_user:
                    break
            received_messages[last_user] = user_count
            return ModelResponse(parts=[TextPart(content=f"ok {last_user}")])

        mock_agent = Agent(FunctionModel(model_fn), output_type=str)
        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = mock_agent  # type: ignore[assignment]
        bot._deps = mock_deps

        try:
            # User A sends 3 messages
            await bot._chat(600, "A-msg-1")
            await bot._chat(600, "A-msg-2")
            await bot._chat(600, "A-msg-3")

            # User B sends 1 message — should NOT see A's history
            await bot._chat(700, "B-msg-1")

            # User B should only see 1 user message, not 4
            assert received_messages["B-msg-1"] == 1
            # User A should see 3 messages on their last turn
            assert received_messages["A-msg-3"] == 3
        finally:
            bot._agent, bot._deps = saved


class TestHistoryTrimming:
    """Test that history trimming preserves important context."""

    def setup_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    def teardown_method(self) -> None:
        from app.assistant import bot

        bot._conversations.clear()
        bot._conversation_last_access.clear()

    @pytest.mark.asyncio
    async def test_history_capped_at_max(self) -> None:
        """History should not exceed _MAX_HISTORY messages."""
        from app.assistant import bot

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        mock_agent = Agent(FunctionModel(model_fn), output_type=str)
        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = mock_agent  # type: ignore[assignment]
        bot._deps = mock_deps

        try:
            # Send many messages to exceed _MAX_HISTORY
            for i in range(50):
                await bot._chat(800, f"Message {i}")

            history = bot._conversations[800]
            # trim_history may keep slightly more than MAX to avoid orphaning tool calls
            assert len(history) <= bot._MAX_HISTORY + 2
        finally:
            bot._agent, bot._deps = saved

    @pytest.mark.asyncio
    async def test_recent_messages_preserved_after_trim(self) -> None:
        """After trimming, the most recent messages should be kept."""
        from app.assistant import bot

        turn = 0

        def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            nonlocal turn
            turn += 1
            return ModelResponse(parts=[TextPart(content=f"turn-{turn}")])

        mock_agent = Agent(FunctionModel(model_fn), output_type=str)
        mock_deps = _make_deps()

        saved = bot._agent, bot._deps
        bot._agent = mock_agent  # type: ignore[assignment]
        bot._deps = mock_deps

        try:
            # Send enough to trigger trimming
            for i in range(50):
                await bot._chat(900, f"Message {i}")

            # The most recent message should still be in history
            history = bot._conversations[900]
            assert _find_text_in_history(history, "Message 49")
        finally:
            bot._agent, bot._deps = saved
