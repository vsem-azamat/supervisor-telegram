"""Format tool call traces from PydanticAI message history into user-visible text.

Used to show which tools the agent called (and their brief results) as part of
a single response message — giving the user visibility into what happened.
"""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

# Human-readable labels for known tools (Russian).
# Tools not in this map fall back to their raw function name.
TOOL_LABELS: dict[str, str] = {
    # ── Review agent ──
    "get_current_post": "Читаю пост",
    "update_post": "Обновляю пост",
    "web_search": "Поиск в интернете",
    "list_images": "Список картинок",
    "use_candidate": "Выбор из пула",
    "add_image_url": "Добавление ссылки на картинку",
    "find_and_add_image": "Поиск и добавление картинки",
    "remove_image": "Удаление картинки",
    "reorder_images": "Переупорядочивание картинок",
    "clear_images": "Очистка картинок",
}

_BRIEF_MAX_LEN = 80


def _brief_result(content: str) -> str:
    """Extract a brief one-liner from tool return content.

    Returns empty string if the content is too long or unhelpful to show inline.
    """
    text = str(content).strip()
    if not text:
        return ""
    first_line = text.split("\n")[0].strip()
    if len(first_line) > _BRIEF_MAX_LEN:
        return ""
    return first_line


def format_tool_trace(
    messages: list[ModelMessage],
    *,
    labels: dict[str, str] | None = None,
) -> str:
    """Extract tool calls from a PydanticAI message list and format as compact trace.

    Pass ``result.new_messages()`` or a slice of ``result.all_messages()`` to show
    only the current turn's tool activity.

    Returns an empty string if no tool calls were made.
    """
    tool_labels = {**TOOL_LABELS, **(labels or {})}

    # Build tool_call_id → return content mapping
    returns: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for req_part in msg.parts:
                if isinstance(req_part, ToolReturnPart):
                    returns[req_part.tool_call_id] = str(req_part.content)

    # Extract tool calls in order
    lines: list[str] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for resp_part in msg.parts:
                if isinstance(resp_part, ToolCallPart):
                    label = tool_labels.get(resp_part.tool_name, resp_part.tool_name)
                    ret = returns.get(resp_part.tool_call_id, "")
                    summary = _brief_result(ret)
                    if summary:
                        lines.append(f"{{🔧 {label}}} ✓ — {summary}")
                    else:
                        lines.append(f"{{🔧 {label}}} ✓")

    return "\n".join(lines)


def format_response_with_trace(
    messages: list[ModelMessage],
    final_text: str,
    *,
    labels: dict[str, str] | None = None,
) -> str:
    """Combine tool trace + final agent text into one formatted response.

    If no tools were called, returns ``final_text`` unchanged.
    """
    trace = format_tool_trace(messages, labels=labels)
    if not trace:
        return final_text
    return f"{trace}\n\n{final_text}"


def make_history_processor(max_messages: int = 40):
    """Create a history processor function for PydanticAI Agent(history_processors=[...])."""

    def processor(messages: list[ModelMessage]) -> list[ModelMessage]:
        return trim_history(messages, max_messages)

    return processor


def trim_history(messages: list[ModelMessage], max_messages: int = 40) -> list[ModelMessage]:
    """Trim conversation history to *max_messages*, respecting tool call boundaries.

    Naive slicing can orphan a ToolCallPart (in a ModelResponse) from its
    ToolReturnPart (in the following ModelRequest), causing LLM errors.
    This function finds the nearest user-message boundary at or before the
    target cut point, so tool call pairs are never split.  May return
    slightly more than *max_messages* to preserve integrity.
    """
    if len(messages) <= max_messages:
        return messages

    # Target: keep messages[0] (system) + tail starting near this index
    target_start = len(messages) - (max_messages - 1)

    # Walk backward from target_start to find a ModelRequest with a UserPromptPart
    for i in range(target_start, 0, -1):
        if isinstance(messages[i], ModelRequest) and any(isinstance(p, UserPromptPart) for p in messages[i].parts):
            return [messages[0]] + messages[i:]

    # Fallback: keep everything (shouldn't happen in practice)
    return messages
