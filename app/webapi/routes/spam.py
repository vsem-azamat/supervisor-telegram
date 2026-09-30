"""Spam ping endpoints — list-only in Phase 3b."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import SpamPingRead
from app.webapi.services.spam_pings import read_pings

router = APIRouter(prefix="/spam", tags=["spam"])


@router.get("/pings", response_model=list[SpamPingRead])
async def list_pings(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    chat_id: Annotated[int | None, Query(description="Filter by chat_id")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Max rows to return")] = 100,
) -> list[SpamPingRead]:
    """Most recent ad-detector hits, newest first; with chat_id, that chat's."""
    return await read_pings(session, chat_id=chat_id, limit=limit)
