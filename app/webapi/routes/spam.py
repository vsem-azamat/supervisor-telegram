"""Spam ping endpoints — list-only in Phase 3b."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chat, SpamPing, User
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import SpamPingRead

router = APIRouter(prefix="/spam", tags=["spam"])


async def read_pings(session: AsyncSession, *, chat_id: int | None, limit: int) -> list[SpamPingRead]:
    """Ad-detector hits, newest first, with the chat's title and the author.

    Chats and users the bot never stored come back without a title or a name;
    an author with no row cannot be on the blacklist either.
    """
    stmt = (
        select(SpamPing, Chat.title, User)
        .join(Chat, Chat.id == SpamPing.chat_id, isouter=True)
        .join(User, User.id == SpamPing.user_id, isouter=True)
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
            username=user.username if user else None,
            first_name=user.first_name if user else None,
            last_name=user.last_name if user else None,
            blocked=bool(user and user.blocked),
            message_id=ping.message_id,
            kind=ping.kind,
            matches=ping.matches,
            snippet=ping.snippet,
            detected_at=ping.detected_at,
        )
        for ping, title, user in rows
    ]


@router.get("/pings", response_model=list[SpamPingRead])
async def list_pings(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    chat_id: Annotated[int | None, Query(description="Filter by chat_id")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Max rows to return")] = 100,
) -> list[SpamPingRead]:
    """Most recent ad-detector hits, newest first; with chat_id, that chat's."""
    return await read_pings(session, chat_id=chat_id, limit=limit)
