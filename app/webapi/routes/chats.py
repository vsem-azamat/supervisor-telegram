"""Chats — list + detail endpoints.

Heatmap is built from the `messages` table (populated by moderator handlers),
not from Telethon. That's intentional: it's fast, always-fresh for moderated
chats, and doesn't burn Telethon rate limits. Telethon only enriches
member_count. For chats the bot hasn't seen, counts will simply be zero —
we do not paper over that with Telethon history fetches in Phase 2.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot, Message
from app.webapi.deps import get_session, get_telethon_stats, require_super_admin
from app.webapi.schemas import ChatDetail, ChatRead, HeatmapCell, MemberSnapshotPoint
from app.webapi.services.telethon_stats import TelethonStatsService

router = APIRouter(prefix="/chats", tags=["chats"])

_HEATMAP_LOOKBACK_DAYS = 7
_HEATMAP_MAX_ROWS = 50_000
_SNAPSHOTS_LIMIT = 50


def _build_heatmap(timestamps: list[datetime.datetime]) -> list[HeatmapCell]:
    grid: dict[tuple[int, int], int] = {}
    for ts in timestamps:
        key = (ts.weekday(), ts.hour)
        grid[key] = grid.get(key, 0) + 1
    return [HeatmapCell(weekday=w, hour=h, count=c) for (w, h), c in sorted(grid.items())]


@router.get("", response_model=list[ChatRead])
async def list_chats(
    session: Annotated[AsyncSession, Depends(get_session)],
    stats: Annotated[TelethonStatsService, Depends(get_telethon_stats)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[ChatRead]:
    chats = (await session.execute(select(Chat).order_by(Chat.title))).scalars().all()
    member_counts = await asyncio.gather(*[stats.get_member_count(c.id) for c in chats])
    return [
        ChatRead(
            id=chat.id,
            title=chat.title,
            is_forum=chat.is_forum,
            is_welcome_enabled=chat.is_welcome_enabled,
            is_captcha_enabled=chat.is_captcha_enabled,
            member_count=member_count,
            created_at=chat.created_at,
        )
        for chat, member_count in zip(chats, member_counts, strict=True)
    ]


@router.get("/{chat_id}", response_model=ChatDetail)
async def get_chat(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    stats: Annotated[TelethonStatsService, Depends(get_telethon_stats)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChatDetail:
    chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

    since = utc_now() - datetime.timedelta(days=_HEATMAP_LOOKBACK_DAYS)
    timestamps_rows = (
        await session.execute(
            select(Message.timestamp)
            .where(Message.chat_id == chat_id)
            .where(Message.timestamp >= since)
            .limit(_HEATMAP_MAX_ROWS)
        )
    ).all()
    timestamps = [row[0] for row in timestamps_rows]

    snapshot_rows = (
        (
            await session.execute(
                select(ChatMemberSnapshot)
                .where(ChatMemberSnapshot.chat_id == chat_id)
                .order_by(ChatMemberSnapshot.captured_at.desc())
                .limit(_SNAPSHOTS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    snapshots_ascending = list(reversed(snapshot_rows))

    member_count = await stats.get_member_count(chat.id)

    return ChatDetail(
        id=chat.id,
        title=chat.title,
        is_forum=chat.is_forum,
        is_welcome_enabled=chat.is_welcome_enabled,
        is_captcha_enabled=chat.is_captcha_enabled,
        member_count=member_count,
        created_at=chat.created_at,
        welcome_message=chat.welcome_message,
        time_delete=chat.time_delete,
        modified_at=chat.modified_at,
        heatmap=_build_heatmap(timestamps),
        member_snapshots=[
            MemberSnapshotPoint(captured_at=s.captured_at, member_count=s.member_count) for s in snapshots_ascending
        ],
    )
