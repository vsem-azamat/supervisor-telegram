"""Agent chat endpoints — Phase 3c.

POST /api/agent/turn streams an SSE response with `tool_call`,
`tool_result`, `token`, `done`, and `error` events. GET /api/agent/history
returns the projected conversation as flat rows. POST /api/agent/clear
drops the persisted row.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConversation
from app.db.session import create_session_maker
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import AgentHistory, AgentMessage, AgentTurnRequest
from app.webapi.services import agent_chat

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/history", response_model=AgentHistory)
async def get_history(
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: Annotated[int, Depends(require_super_admin)],
) -> AgentHistory:
    rows = await agent_chat.get_history_for_ui(session, admin_id)
    msg_count = (
        await session.execute(select(AgentConversation.message_count).where(AgentConversation.user_id == admin_id))
    ).scalar_one_or_none() or 0
    return AgentHistory(
        user_id=admin_id,
        message_count=int(msg_count),
        messages=[AgentMessage(**row) for row in rows],
    )


@router.post("/clear", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversation(
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: Annotated[int, Depends(require_super_admin)],
) -> Response:
    await agent_chat.clear_history(session, admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/turn")
async def turn(
    body: AgentTurnRequest,
    admin_id: Annotated[int, Depends(require_super_admin)],
) -> StreamingResponse:
    """SSE stream of one agent turn.

    We open a fresh session_maker session inside the generator so the
    long-lived connection isn't tied to the request's get_session
    lifecycle (which closes when the route returns — generator continues
    afterwards).
    """
    session_maker = create_session_maker()

    async def event_stream() -> AsyncGenerator[bytes, None]:
        async with session_maker() as session:
            try:
                async for event in agent_chat.stream_turn(session=session, user_id=admin_id, user_text=body.message):
                    yield _sse_frame(event)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                yield _sse_frame({"type": "error", "message": str(err) or "agent stream failed"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_frame(event: dict[str, object]) -> bytes:
    payload = json.dumps(event, ensure_ascii=False)
    return f"event: {event.get('type', 'message')}\ndata: {payload}\n\n".encode()
