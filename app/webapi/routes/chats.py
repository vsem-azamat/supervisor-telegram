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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot, Message, SpamPing, User
from app.webapi.deps import get_session, get_telethon_stats, require_super_admin
from app.webapi.schemas import (
    ChatDetail,
    ChatNode,
    ChatRead,
    ChatSender,
    HeatmapCell,
    MemberSnapshotPoint,
    SpamPingRead,
)
from app.webapi.services.telethon_stats import TelethonStatsService

router = APIRouter(prefix="/chats", tags=["chats"])

_HEATMAP_LOOKBACK_DAYS = 7
_HEATMAP_MAX_ROWS = 50_000
_SNAPSHOTS_LIMIT = 50
_SPAM_PINGS_LIMIT = 30
_RECENT_SENDERS_LOOKBACK_DAYS = 7
_RECENT_SENDERS_LIMIT = 25


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
            parent_chat_id=chat.parent_chat_id,
            relation_notes=chat.relation_notes,
            member_count=member_count,
            created_at=chat.created_at,
        )
        for chat, member_count in zip(chats, member_counts, strict=True)
    ]


@router.get("/graph", response_model=list[ChatNode])
async def get_chat_graph(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[ChatNode]:
    """Return chat tree with roots first; children nested via parent_chat_id.

    Single SQL query; tree assembly is in-memory. Telethon enrichment is
    intentionally skipped for the tree endpoint — tile renders 1+ times
    per poll, member_count drilldown lives on /chats/:id.

    Self-loops (parent_chat_id == id) and orphans (parent_chat_id points
    to a missing/deleted chat) become roots; multi-hop cycles aren't
    detected here — admins set parent_chat_id manually so cycles would
    be intentional misuse, not a runtime hazard.
    """
    chats = (await session.execute(select(Chat))).scalars().all()
    by_id: dict[int, ChatNode] = {
        c.id: ChatNode(id=c.id, title=c.title, relation_notes=c.relation_notes, children=[]) for c in chats
    }
    roots: list[ChatNode] = []
    for c in chats:
        node = by_id[c.id]
        parent_id = c.parent_chat_id
        if parent_id is not None and parent_id != c.id and parent_id in by_id:
            by_id[parent_id].children.append(node)
        else:
            roots.append(node)

    def _key(n: ChatNode) -> tuple[str, int]:
        return ((n.title or "").lower(), n.id)

    def _sort(nodes: list[ChatNode]) -> None:
        nodes.sort(key=_key)
        for n in nodes:
            _sort(n.children)

    _sort(roots)
    return roots


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

    children_rows = (
        (await session.execute(select(Chat).where(Chat.parent_chat_id == chat_id).order_by(Chat.title))).scalars().all()
    )
    children_nodes = [
        ChatNode(id=c.id, title=c.title, relation_notes=c.relation_notes, children=[]) for c in children_rows
    ]

    spam_rows = (
        (
            await session.execute(
                select(SpamPing)
                .where(SpamPing.chat_id == chat_id)
                .order_by(SpamPing.detected_at.desc())
                .limit(_SPAM_PINGS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    spam_pings = [
        SpamPingRead(
            id=p.id,
            chat_id=p.chat_id,
            chat_title=chat.title,
            user_id=p.user_id,
            message_id=p.message_id,
            kind=p.kind,
            matches=p.matches,
            snippet=p.snippet,
            detected_at=p.detected_at,
        )
        for p in spam_rows
    ]

    senders_since = utc_now() - datetime.timedelta(days=_RECENT_SENDERS_LOOKBACK_DAYS)
    senders_rows = (
        await session.execute(
            select(
                Message.user_id,
                func.count(Message.id).label("message_count"),
                func.max(Message.timestamp).label("last_seen"),
                User.username,
                User.first_name,
                User.last_name,
                User.blocked,
            )
            .outerjoin(User, User.id == Message.user_id)
            .where(Message.chat_id == chat_id)
            .where(Message.timestamp >= senders_since)
            .group_by(Message.user_id, User.username, User.first_name, User.last_name, User.blocked)
            .order_by(func.count(Message.id).desc())
            .limit(_RECENT_SENDERS_LIMIT)
        )
    ).all()
    recent_senders = [
        ChatSender(
            user_id=r.user_id,
            username=r.username,
            first_name=r.first_name,
            last_name=r.last_name,
            message_count=int(r.message_count),
            last_seen=r.last_seen,
            blocked=bool(r.blocked) if r.blocked is not None else False,
        )
        for r in senders_rows
    ]

    return ChatDetail(
        id=chat.id,
        title=chat.title,
        is_forum=chat.is_forum,
        is_welcome_enabled=chat.is_welcome_enabled,
        is_captcha_enabled=chat.is_captcha_enabled,
        parent_chat_id=chat.parent_chat_id,
        relation_notes=chat.relation_notes,
        member_count=member_count,
        created_at=chat.created_at,
        welcome_message=chat.welcome_message,
        time_delete=chat.time_delete,
        modified_at=chat.modified_at,
        heatmap=_build_heatmap(timestamps),
        member_snapshots=[
            MemberSnapshotPoint(captured_at=s.captured_at, member_count=s.member_count) for s in snapshots_ascending
        ],
        children=children_nodes,
        spam_pings=spam_pings,
        recent_senders=recent_senders,
    )
