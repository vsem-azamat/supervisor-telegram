"""Spam ping endpoints — list-only in Phase 3b."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, SpamPing
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import SpamPingRead

router = APIRouter(prefix="/spam", tags=["spam"])


@router.get("/pings", response_model=list[SpamPingRead])
async def list_pings(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    chat_id: Annotated[int | None, Query(description="Filter by chat_id")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Max rows to return")] = 100,
) -> list[SpamPingRead]:
    """Most recent ad-detector hits, newest first.

    With chat_id, filters to that chat. Joined against Chat to surface
    the title; chats not in the table (untracked groups) come back with
    chat_title = None.
    """
    stmt = (
        select(SpamPing, Chat.title)
        .join(Chat, Chat.id == SpamPing.chat_id, isouter=True)
        .order_by(SpamPing.detected_at.desc())
        .limit(limit)
    )
    if chat_id is not None:
        stmt = stmt.where(SpamPing.chat_id == chat_id)

    rows = (await session.execute(stmt)).all()
    return [
        SpamPingRead(
            id=ping.id,
            chat_id=ping.chat_id,
            chat_title=title,
            user_id=ping.user_id,
            message_id=ping.message_id,
            kind=ping.kind,
            matches=ping.matches,
            snippet=ping.snippet,
            detected_at=ping.detected_at,
        )
        for ping, title in rows
    ]
