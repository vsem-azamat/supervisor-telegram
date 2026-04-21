"""Web `/agent` chat — persistence + streaming wrapper.

Wraps the existing PydanticAI assistant agent (`create_assistant_agent`)
for SSE consumption from the web UI:

  * Conversation history is JSON-serialised via `ModelMessagesTypeAdapter`
    and stored per-user in `agent_conversations` (one row per admin).
  * `stream_turn` runs one user turn, yielding plain dicts that the
    SSE route translates to `text/event-stream` frames.
  * Idle eviction runs at the start of every turn (cheap query).

The webapi process doesn't host a live aiogram Bot, so we hand the agent
a `_StubBot` for `AssistantDeps.main_bot`. Read-only tools never touch
it; moderation / send-message tools attempt to call a method, hit the
guard, and surface a clean error to the LLM instead of crashing the
stream. Phase 4 will route those mutations through a different transport.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sqlalchemy import select

from app.assistant.agent import AssistantDeps, create_assistant_agent
from app.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage
from app.core.config import settings
from app.core.container import container
from app.core.logging import get_logger
from app.core.time import utc_now
from app.core.tool_trace import TOOL_LABELS
from app.db.models import AgentConversation
from app.db.session import create_session_maker

if TYPE_CHECKING:
    from aiogram import Bot
    from pydantic_ai import Agent
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger("webapi.agent_chat")


class _StubBot:
    """Stand-in for `aiogram.Bot` when running outside the bot process.

    Any attribute access raises a clear runtime error. Tools that catch
    `Exception` (most do) will report the failure back to the LLM, which
    then explains the limitation to the user. Tools that don't catch
    will fail the turn with a useful message.
    """

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(
            f"main_bot is unavailable in the web /agent process — tool tried to call .{name}. "
            "Use the assistant bot in Telegram for actions that send messages."
        )


_AGENT_TURN_TIMEOUT_SECONDS = 180
_IDLE_TTL_SECONDS = 4 * 3600
_TEXT_DEBOUNCE_SECONDS = 0.05

_agent: Agent[AssistantDeps, str] | None = None
_deps: AssistantDeps | None = None


def _ensure_agent() -> tuple[Agent[AssistantDeps, str], AssistantDeps]:
    global _agent, _deps  # noqa: PLW0603
    if _agent is None or _deps is None:
        _agent = create_assistant_agent()
        try:
            session_maker = container.get_session_maker()
        except ValueError:
            session_maker = create_session_maker()
        live_bot = container.try_get_bot()
        main_bot = live_bot if live_bot is not None else cast("Bot", _StubBot())
        _deps = AssistantDeps(
            session_maker=session_maker,
            main_bot=main_bot,
            review_bot=None,
            channel_orchestrator=container.get_channel_orchestrator(),
            telethon=container.get_telethon_client(),
        )
    return _agent, _deps


def _serialize(messages: list[ModelMessage]) -> list[Any]:
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")


def _deserialize(blob: list[Any] | None) -> list[ModelMessage]:
    if not blob:
        return []
    return ModelMessagesTypeAdapter.validate_python(blob)


# ---------------------------------------------------------------------------
# UI-facing message shape
# ---------------------------------------------------------------------------

UiMessageRole = Literal["user", "assistant", "tool"]


def serialize_for_ui(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Project PydanticAI messages onto a flat list the chat UI can render.

    User prompts and assistant text become `role="user"` / `role="assistant"`
    rows; tool calls collapse into a compact `role="tool"` row paired with
    the matching return content (one per call).
    """
    returns: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    returns[part.tool_call_id] = str(part.content)

    out: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    text = part.content if isinstance(part.content, str) else str(part.content)
                    out.append({"role": "user", "text": text})
        elif isinstance(msg, ModelResponse):
            text_chunks: list[str] = []
            for part in msg.parts:
                if isinstance(part, TextPart) and part.content:
                    text_chunks.append(part.content)
                elif isinstance(part, ToolCallPart):
                    label = TOOL_LABELS.get(part.tool_name, part.tool_name)
                    out.append(
                        {
                            "role": "tool",
                            "tool_name": part.tool_name,
                            "tool_label": label,
                            "result_preview": _short(returns.get(part.tool_call_id, "")),
                        }
                    )
            if text_chunks:
                out.append({"role": "assistant", "text": "".join(text_chunks)})
    return out


def _short(text: str, limit: int = 200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def load_history(session: AsyncSession, user_id: int) -> tuple[list[ModelMessage], AgentConversation | None]:
    row = (
        await session.execute(select(AgentConversation).where(AgentConversation.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        return [], None
    return _deserialize(row.messages), row


async def get_history_for_ui(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    messages, _ = await load_history(session, user_id)
    return serialize_for_ui(messages)


async def clear_history(session: AsyncSession, user_id: int) -> bool:
    row = (
        await session.execute(select(AgentConversation).where(AgentConversation.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def _evict_idle(session: AsyncSession, *, now: datetime.datetime) -> None:
    """Drop conversations idle past the TTL. Cheap — uses indexed last_active_at."""
    cutoff = now - datetime.timedelta(seconds=_IDLE_TTL_SECONDS)
    rows = (
        (await session.execute(select(AgentConversation).where(AgentConversation.last_active_at < cutoff)))
        .scalars()
        .all()
    )
    for r in rows:
        await session.delete(r)


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


async def stream_turn(
    *,
    session: AsyncSession,
    user_id: int,
    user_text: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run one turn; yield SSE-ready event dicts.

    Event shapes (`type` discriminates):
      * `{"type": "tool_call", "tool_name", "label"}`
      * `{"type": "tool_result", "tool_name", "result_preview"}`
      * `{"type": "token", "text"}`            # cumulative text-so-far
      * `{"type": "done", "final_text", "message_count"}`
      * `{"type": "error", "message"}`

    The DB write happens after the agent finishes; consumers must drain
    the generator to ensure history is persisted.
    """
    agent, deps = _ensure_agent()

    now = utc_now()
    await _evict_idle(session, now=now)
    history, _row = await load_history(session, user_id)

    pending_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sentinel: dict[str, Any] = {"type": "__done__"}

    # Track tool_call_id → tool_name so tool_result events can carry both
    pending_tools: dict[str, str] = {}

    async def _tool_event_handler(_ctx: Any, events: Any) -> None:
        async for event in events:
            if isinstance(event, FunctionToolCallEvent):
                tool_name = event.part.tool_name
                label = TOOL_LABELS.get(tool_name, tool_name)
                pending_tools[event.part.tool_call_id] = tool_name
                await pending_events.put(
                    {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "tool_call_id": event.part.tool_call_id,
                        "label": label,
                    }
                )
            elif isinstance(event, FunctionToolResultEvent):
                content = getattr(event, "content", None)
                preview = _short(str(content)) if content is not None else ""
                tool_name = pending_tools.pop(event.tool_call_id, "")
                await pending_events.put(
                    {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "tool_call_id": event.tool_call_id,
                        "result_preview": preview,
                    }
                )

    async def _run_agent() -> tuple[str, list[ModelMessage]]:
        async with asyncio.timeout(_AGENT_TURN_TIMEOUT_SECONDS):
            async with agent.run_stream(
                user_text,
                deps=deps,
                message_history=history,
                event_stream_handler=_tool_event_handler,
            ) as stream:
                async for chunk in stream.stream_text(debounce_by=_TEXT_DEBOUNCE_SECONDS):
                    await pending_events.put({"type": "token", "text": chunk})
                final = await stream.get_output()
                usage = extract_usage_from_pydanticai_result(stream, settings.assistant.model, "assistant_chat")
                if usage:
                    await log_usage(usage)
                all_msgs = list(stream.all_messages())
                return final, all_msgs

    runner = asyncio.create_task(_run_agent())

    async def _drain() -> None:
        try:
            await runner
        except BaseException:  # noqa: BLE001, S110
            # Error propagates via `runner` itself; drainer's only job is to
            # unblock the consumer loop with the sentinel.
            pass
        finally:
            await pending_events.put(sentinel)

    drainer = asyncio.create_task(_drain())

    try:
        while True:
            event = await pending_events.get()
            if event is sentinel:
                break
            yield event

        # Normal completion path: surface agent result, persist, emit "done".
        try:
            final_text, all_msgs = await runner
        except Exception as err:  # noqa: BLE001
            logger.exception("agent_turn_failed", user_id=user_id)
            yield {"type": "error", "message": str(err) or "Agent run failed"}
            return

        await _persist(session, user_id=user_id, messages=all_msgs, now=utc_now())
        yield {
            "type": "done",
            "final_text": final_text,
            "message_count": len(all_msgs),
        }
    finally:
        # If consumer disconnected mid-stream, cancel the agent so it doesn't
        # keep burning tokens past a closed connection.
        if not runner.done():
            runner.cancel()
        with contextlib.suppress(asyncio.CancelledError, BaseException):
            await runner
        if not drainer.done():
            drainer.cancel()
        with contextlib.suppress(asyncio.CancelledError, BaseException):
            await drainer


async def _persist(
    session: AsyncSession,
    *,
    user_id: int,
    messages: list[ModelMessage],
    now: datetime.datetime,
) -> None:
    blob = _serialize(messages)
    row = (
        await session.execute(select(AgentConversation).where(AgentConversation.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        row = AgentConversation(
            user_id=user_id,
            messages=blob,
            message_count=len(messages),
            last_active_at=now,
            created_at=now,
        )
        session.add(row)
    else:
        row.messages = blob
        row.message_count = len(messages)
        row.last_active_at = now
    await session.commit()
