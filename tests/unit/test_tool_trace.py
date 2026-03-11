"""Tests for app.agent.tool_trace — tool call trace formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agent.tool_trace import format_response_with_trace, format_tool_trace, trim_history
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import RequestUsage


def _usage() -> RequestUsage:
    return RequestUsage()


def _ts() -> datetime:
    return datetime.now(tz=UTC)


class TestFormatToolTrace:
    def test_no_tool_calls_returns_empty(self) -> None:
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="hello")]),
            ModelResponse(parts=[TextPart(content="hi")], usage=_usage(), timestamp=_ts()),
        ]
        assert format_tool_trace(msgs) == ""

    def test_single_tool_call(self) -> None:
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="сократи")]),
            ModelResponse(
                parts=[
                    TextPart(content="Сейчас сделаю"),
                    ToolCallPart(tool_name="get_current_post", args={}, tool_call_id="tc1"),
                ],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(
                parts=[ToolReturnPart(tool_name="get_current_post", content="Post text here", tool_call_id="tc1")]
            ),
            ModelResponse(parts=[TextPart(content="Готово")], usage=_usage(), timestamp=_ts()),
        ]
        trace = format_tool_trace(msgs)
        assert "{🔧 Читаю пост} ✓ — Post text here" in trace

    def test_multiple_tool_calls(self) -> None:
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="сократи")]),
            ModelResponse(
                parts=[ToolCallPart(tool_name="get_current_post", args={}, tool_call_id="tc1")],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="get_current_post", content="Long post text\nwith lines", tool_call_id="tc1"
                    )
                ]
            ),
            ModelResponse(
                parts=[ToolCallPart(tool_name="update_post", args={"new_text": "short"}, tool_call_id="tc2")],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(
                parts=[ToolReturnPart(tool_name="update_post", content="Post updated (300 chars).", tool_call_id="tc2")]
            ),
            ModelResponse(parts=[TextPart(content="Готово")], usage=_usage(), timestamp=_ts()),
        ]
        trace = format_tool_trace(msgs)
        lines = trace.strip().split("\n")
        assert len(lines) == 2
        assert "Читаю пост" in lines[0]
        assert "Обновляю пост" in lines[1]
        assert "Post updated (300 chars)." in lines[1]

    def test_long_return_value_hidden(self) -> None:
        """Tool returns >80 chars on first line should show just ✓ without summary."""
        long_content = "x" * 100
        msgs: list[ModelMessage] = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="get_current_post", args={}, tool_call_id="tc1")],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(
                parts=[ToolReturnPart(tool_name="get_current_post", content=long_content, tool_call_id="tc1")]
            ),
        ]
        trace = format_tool_trace(msgs)
        assert trace == "{🔧 Читаю пост} ✓"
        assert "—" not in trace

    def test_unknown_tool_uses_raw_name(self) -> None:
        msgs: list[ModelMessage] = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="my_custom_tool", args={}, tool_call_id="tc1")],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(parts=[ToolReturnPart(tool_name="my_custom_tool", content="ok", tool_call_id="tc1")]),
        ]
        trace = format_tool_trace(msgs)
        assert "my_custom_tool" in trace

    def test_custom_labels(self) -> None:
        msgs: list[ModelMessage] = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="my_tool", args={}, tool_call_id="tc1")],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(parts=[ToolReturnPart(tool_name="my_tool", content="done", tool_call_id="tc1")]),
        ]
        trace = format_tool_trace(msgs, labels={"my_tool": "Мой инструмент"})
        assert "Мой инструмент" in trace


class TestFormatResponseWithTrace:
    def test_no_tools_returns_text_unchanged(self) -> None:
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="привет")]),
            ModelResponse(parts=[TextPart(content="Привет!")], usage=_usage(), timestamp=_ts()),
        ]
        assert format_response_with_trace(msgs, "Привет!") == "Привет!"

    def test_with_tools_prepends_trace(self) -> None:
        msgs: list[ModelMessage] = [
            ModelResponse(
                parts=[ToolCallPart(tool_name="web_search", args={"query": "test"}, tool_call_id="tc1")],
                usage=_usage(),
                timestamp=_ts(),
            ),
            ModelRequest(parts=[ToolReturnPart(tool_name="web_search", content="Results found", tool_call_id="tc1")]),
            ModelResponse(parts=[TextPart(content="Вот что нашёл")], usage=_usage(), timestamp=_ts()),
        ]
        result = format_response_with_trace(msgs, "Вот что нашёл")
        assert result.startswith("{🔧")
        assert "Вот что нашёл" in result
        # Trace and text should be separated by double newline
        assert "\n\n" in result

    def test_empty_messages_returns_text(self) -> None:
        assert format_response_with_trace([], "hello") == "hello"


class TestTrimHistory:
    def test_no_trim_when_under_limit(self) -> None:
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="hi")]),
            ModelResponse(parts=[TextPart(content="hello")], usage=_usage(), timestamp=_ts()),
        ]
        result = trim_history(msgs, max_messages=10)
        assert len(result) == 2

    def test_trim_preserves_first_message(self) -> None:
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="system")]),  # first msg — keep
        ]
        # Add enough messages to exceed limit
        for i in range(10):
            msgs.append(ModelRequest(parts=[UserPromptPart(content=f"user_{i}")]))
            msgs.append(ModelResponse(parts=[TextPart(content=f"resp_{i}")], usage=_usage(), timestamp=_ts()))

        result = trim_history(msgs, max_messages=6)
        assert len(result) <= 7  # first + up to 6
        # First message preserved
        first = result[0]
        assert isinstance(first, ModelRequest)
        assert any(isinstance(p, UserPromptPart) and p.content == "system" for p in first.parts)

    def test_trim_skips_orphaned_tool_returns(self) -> None:
        """Trimming should not start at a ToolReturnPart — skip to next user message."""
        msgs: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="system")]),  # [0] keep
            ModelRequest(parts=[UserPromptPart(content="old user msg")]),  # [1]
            ModelResponse(parts=[TextPart(content="old resp")], usage=_usage(), timestamp=_ts()),  # [2]
            # Tool call pair — must not be split
            ModelRequest(parts=[UserPromptPart(content="edit this")]),  # [3]
            ModelResponse(
                parts=[ToolCallPart(tool_name="get_current_post", args={}, tool_call_id="tc1")],
                usage=_usage(),
                timestamp=_ts(),
            ),  # [4]
            ModelRequest(
                parts=[ToolReturnPart(tool_name="get_current_post", content="post text", tool_call_id="tc1")]
            ),  # [5] — orphan danger!
            ModelResponse(parts=[TextPart(content="done")], usage=_usage(), timestamp=_ts()),  # [6]
        ]
        # With max_messages=4, naive slice would be [0] + msgs[-3:] = [0, 4, 5, 6]
        # msg[4] is a ToolCallPart response, msg[5] is its ToolReturnPart — but
        # msg[3] (the user prompt that initiated the call) would be missing.
        # trim_history should walk back to include msg[3].
        result = trim_history(msgs, max_messages=4)
        # The first message after system must be a user prompt, not mid-tool-call
        first_after_system = result[1]
        assert isinstance(first_after_system, ModelRequest)
        assert any(isinstance(p, UserPromptPart) for p in first_after_system.parts), (
            "First message after system should be a user prompt, not an orphaned tool return"
        )
