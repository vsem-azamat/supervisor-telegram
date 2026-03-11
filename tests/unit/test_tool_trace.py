"""Tests for app.agent.tool_trace — tool call trace formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agent.tool_trace import format_response_with_trace, format_tool_trace
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
