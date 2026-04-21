"""Tests for /api/agent endpoints + agent_chat service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from app.core.config import settings
from app.db.models import AgentConversation
from app.webapi.main import app
from app.webapi.services import agent_chat
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session, get_telethon

    async def _override_get_session():
        async with db_session_maker() as session:
            yield session

    async def _override_get_telethon():
        return None

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_telethon] = _override_get_telethon
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_telethon, None)


async def test_history_empty_returns_zero(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/agent/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == 1
    assert body["message_count"] == 0
    assert body["messages"] == []


async def test_clear_on_empty_conversation_returns_204(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.post("/api/agent/clear")
    assert resp.status_code == 204


async def test_clear_removes_persisted_row(client_factory, db_session_maker) -> None:
    async with db_session_maker() as session:
        session.add(AgentConversation(user_id=1, messages=[{"kind": "x"}], message_count=1))
        await session.commit()

    async with client_factory() as client:
        resp = await client.post("/api/agent/clear")
    assert resp.status_code == 204

    async with db_session_maker() as session:
        from sqlalchemy import select

        row = (
            await session.execute(select(AgentConversation).where(AgentConversation.user_id == 1))
        ).scalar_one_or_none()
    assert row is None


async def test_history_returns_persisted_messages_after_save(client_factory, db_session_maker) -> None:
    """Round-trip: save real PydanticAI messages, then read them back via the API."""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    msgs = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[TextPart(content="hello!")]),
    ]
    async with db_session_maker() as session:
        await agent_chat._persist(  # noqa: SLF001
            session,
            user_id=1,
            messages=msgs,
            now=__import__("datetime").datetime(2026, 4, 22, 0, 0, 0),
        )

    async with client_factory() as client:
        resp = await client.get("/api/agent/history")
    body = resp.json()
    assert body["message_count"] == 2
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["user", "assistant"]
    assert body["messages"][0]["text"] == "hi"
    assert body["messages"][1]["text"] == "hello!"


def test_serialize_for_ui_handles_tool_call_pair() -> None:
    """Tool calls + their returns collapse into a single role='tool' row."""
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    messages: list[Any] = [
        ModelRequest(parts=[UserPromptPart(content="list channels please")]),
        ModelResponse(
            parts=[
                ToolCallPart(tool_name="list_channels", args={}, tool_call_id="call_1"),
            ]
        ),
        ModelRequest(parts=[ToolReturnPart(tool_name="list_channels", content="ch1, ch2", tool_call_id="call_1")]),
        ModelResponse(parts=[TextPart(content="here are your channels: ch1, ch2")]),
    ]
    rows = agent_chat.serialize_for_ui(messages)
    assert [r["role"] for r in rows] == ["user", "tool", "assistant"]
    assert rows[1]["tool_name"] == "list_channels"
    assert rows[1]["result_preview"] == "ch1, ch2"
    assert rows[2]["text"] == "here are your channels: ch1, ch2"


async def test_turn_streams_mocked_events(client_factory, monkeypatch) -> None:
    """The SSE route formats whatever the service yields into text/event-stream frames."""

    async def fake_stream_turn(*, session, user_id, user_text):  # noqa: ARG001
        yield {"type": "tool_call", "tool_name": "list_channels", "tool_call_id": "c1", "label": "List"}
        yield {"type": "tool_result", "tool_name": "list_channels", "tool_call_id": "c1", "result_preview": "ok"}
        yield {"type": "token", "text": "Done."}
        yield {"type": "done", "final_text": "Done.", "message_count": 4}

    monkeypatch.setattr(agent_chat, "stream_turn", fake_stream_turn)

    async with client_factory() as client:
        resp = await client.post("/api/agent/turn", json={"message": "hi"})
        assert resp.status_code == 200
        body = resp.text

    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert "event: token" in body
    assert "event: done" in body
    # Each frame has a JSON data line
    assert body.count("data: {") == 4
