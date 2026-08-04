"""Chats — list + detail endpoints.

Reads, mostly from our own tables. The heatmap comes from the `messages` rows
the moderator handlers write, and member counts from the snapshots the bot
records hourly — asking Telegram once per chat per page load would be a
rate-limit waiting for a second browser tab.

The one exception is the refresh endpoint, which exists to ask.

A chat the bot has never seen carries `None` rather than a zero: not measured
and empty are different claims.
"""

from __future__ import annotations

import datetime
import io
from typing import Annotated, cast

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chats.metadata import fetch_member_count, fetch_metadata
from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot, Message, SpamPing, User
from app.webapi.deps import (
    get_publish_bot,
    get_session,
    require_super_admin,
)
from app.webapi.schemas import (
    ChatDetail,
    ChatNode,
    ChatRead,
    ChatResourceStatus,
    ChatSender,
    ChatUpdate,
    HeatmapCell,
    MemberSnapshotPoint,
    SpamPingRead,
)
from app.webapi.services import member_counts

logger = get_logger("webapi.routes.chats")

router = APIRouter(prefix="/chats", tags=["chats"])

_HEATMAP_LOOKBACK_DAYS = 7
_HEATMAP_MAX_ROWS = 50_000
_SNAPSHOTS_LIMIT = 50
_SPAM_PINGS_LIMIT = 30
_RECENT_SENDERS_LOOKBACK_DAYS = 7
_RECENT_SENDERS_LIMIT = 25


def _resource_status(status: str) -> ChatResourceStatus:
    return cast("ChatResourceStatus", status)


def _build_heatmap(timestamps: list[datetime.datetime]) -> list[HeatmapCell]:
    grid: dict[tuple[int, int], int] = {}
    for ts in timestamps:
        key = (ts.weekday(), ts.hour)
        grid[key] = grid.get(key, 0) + 1
    return [HeatmapCell(weekday=w, hour=h, count=c) for (w, h), c in sorted(grid.items())]


@router.get("", response_model=list[ChatRead])
async def list_chats(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[ChatRead]:
    chats = (await session.execute(select(Chat).order_by(Chat.title))).scalars().all()
    counts = await member_counts.latest_for(session, [chat.id for chat in chats])
    return [
        ChatRead(
            id=chat.id,
            title=chat.title,
            resource_status=_resource_status(chat.resource_status),
            is_forum=chat.is_forum,
            is_welcome_enabled=chat.is_welcome_enabled,
            is_captcha_enabled=chat.is_captcha_enabled,
            is_service_cleanup_enabled=chat.is_service_cleanup_enabled,
            parent_chat_id=chat.parent_chat_id,
            relation_notes=chat.relation_notes,
            public_link=chat.public_link,
            member_count=counts.get(chat.id),
            has_photo=chat.photo_file_id is not None,
            last_synced_at=chat.last_synced_at,
            created_at=chat.created_at,
        )
        for chat in chats
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
        c.id: ChatNode(
            id=c.id,
            title=c.title,
            relation_notes=c.relation_notes,
            has_photo=c.photo_file_id is not None,
            children=[],
        )
        for c in chats
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

    member_count = await member_counts.latest(session, chat.id)

    children_rows = (
        (await session.execute(select(Chat).where(Chat.parent_chat_id == chat_id).order_by(Chat.title))).scalars().all()
    )
    children_nodes = [
        ChatNode(
            id=c.id,
            title=c.title,
            relation_notes=c.relation_notes,
            has_photo=c.photo_file_id is not None,
            children=[],
        )
        for c in children_rows
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
        resource_status=_resource_status(chat.resource_status),
        is_forum=chat.is_forum,
        is_welcome_enabled=chat.is_welcome_enabled,
        is_captcha_enabled=chat.is_captcha_enabled,
        is_service_cleanup_enabled=chat.is_service_cleanup_enabled,
        parent_chat_id=chat.parent_chat_id,
        relation_notes=chat.relation_notes,
        public_link=chat.public_link,
        member_count=member_count,
        has_photo=chat.photo_file_id is not None,
        last_synced_at=chat.last_synced_at,
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


@router.patch("/{chat_id}", response_model=ChatRead)
async def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChatRead:
    chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

    fields = payload.model_dump(exclude_unset=True)
    if "time_delete" in fields and fields["time_delete"] is not None and fields["time_delete"] <= 0:
        raise HTTPException(status_code=422, detail="time_delete must be positive")
    if "resource_status" in fields and fields["resource_status"] is not None:
        status: ChatResourceStatus = fields["resource_status"]
        if status not in Chat.VALID_RESOURCE_STATUSES:
            raise HTTPException(status_code=422, detail="Unknown resource status")
    if "parent_chat_id" in fields and fields["parent_chat_id"] == chat_id:
        raise HTTPException(status_code=422, detail="A chat cannot be its own parent")
    if "parent_chat_id" in fields and fields["parent_chat_id"] is not None:
        parent_id = fields["parent_chat_id"]
        parent_rows = (
            await session.execute(select(Chat.id, Chat.parent_chat_id).where(Chat.id.in_([chat_id, parent_id])))
        ).all()
        known_ids = {row.id for row in parent_rows}
        if parent_id not in known_ids:
            raise HTTPException(status_code=422, detail=f"Parent chat {parent_id} not found")

        all_links = (await session.execute(select(Chat.id, Chat.parent_chat_id))).all()
        parent_by_id = {row.id: row.parent_chat_id for row in all_links}
        parent_by_id[chat_id] = parent_id
        seen: set[int] = set()
        cursor = parent_id
        while cursor is not None:
            if cursor == chat_id or cursor in seen:
                raise HTTPException(status_code=422, detail="Chat hierarchy cannot contain cycles")
            seen.add(cursor)
            cursor = parent_by_id.get(cursor)

    for key, value in fields.items():
        setattr(chat, key, value)
    await session.commit()
    await session.refresh(chat)

    member_count = await member_counts.latest(session, chat.id)
    return ChatRead(
        id=chat.id,
        title=chat.title,
        resource_status=_resource_status(chat.resource_status),
        is_forum=chat.is_forum,
        is_welcome_enabled=chat.is_welcome_enabled,
        is_captcha_enabled=chat.is_captcha_enabled,
        is_service_cleanup_enabled=chat.is_service_cleanup_enabled,
        parent_chat_id=chat.parent_chat_id,
        relation_notes=chat.relation_notes,
        public_link=chat.public_link,
        member_count=member_count,
        has_photo=chat.photo_file_id is not None,
        last_synced_at=chat.last_synced_at,
        created_at=chat.created_at,
    )


@router.get("/{chat_id}/avatar")
async def get_chat_avatar(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Annotated[Bot, Depends(get_publish_bot)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> StreamingResponse:
    """Stream the chat's avatar JPEG.

    Reads the cached ``photo_file_id`` from the row, calls Bot API
    ``getFile`` to resolve the file_path, then proxies ``download_file``
    bytes back to the client. We proxy rather than 302-redirecting because
    the Telegram file URL contains the bot token; redirecting would leak it.

    Browsers cache the response for 1h via Cache-Control. Cached bytes
    invalidate naturally when ``photo_file_id`` changes (the URL stays the
    same but the bytes don't — we accept the staleness window since the
    icon swap on rename is a low-impact event for an admin tool).
    """
    chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")
    if chat.photo_file_id is None:
        raise HTTPException(status_code=404, detail="No avatar cached")

    try:
        downloaded = await bot.download(chat.photo_file_id)
    except TelegramBadRequest as e:
        # File expired upstream — clear cache so next sync re-pulls.
        logger.warning("avatar download failed", chat_id=chat_id, error=str(e))
        chat.photo_file_id = None
        await session.commit()
        raise HTTPException(status_code=404, detail="Avatar unavailable") from None

    if downloaded is None:
        raise HTTPException(status_code=404, detail="Avatar unavailable")

    payload = downloaded.read()
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/{chat_id}/refresh", response_model=ChatRead)
async def refresh_chat_from_telegram(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    bot: Annotated[Bot, Depends(get_publish_bot)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> ChatRead:
    """Pull the title and photo from Telegram now, for one chat.

    Manual counterpart to the hourly loop, and over the same Bot API call.
    The title leg used to go through Telethon, which this process has never
    had — so the button refreshed the photo, bumped the timestamp, and left
    the title exactly as it was.

    The member count comes back fresh here, because somebody who pressed a
    button marked "refresh" is entitled to a number that moved. The loop is
    what writes the row; this reads past it.
    """
    chat = (await session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

    metadata = await fetch_metadata(bot=bot, chat_id=chat_id)
    if metadata is not None:
        if metadata.title and metadata.title != chat.title:
            chat.title = metadata.title
        if metadata.photo_file_id and metadata.photo_file_id != chat.photo_file_id:
            chat.photo_file_id = metadata.photo_file_id

    chat.last_synced_at = utc_now()
    await session.commit()
    await session.refresh(chat)

    member_count = await fetch_member_count(bot=bot, chat_id=chat.id)
    if member_count is None:
        member_count = await member_counts.latest(session, chat.id)
    return ChatRead(
        id=chat.id,
        title=chat.title,
        resource_status=_resource_status(chat.resource_status),
        is_forum=chat.is_forum,
        is_welcome_enabled=chat.is_welcome_enabled,
        is_captcha_enabled=chat.is_captcha_enabled,
        is_service_cleanup_enabled=chat.is_service_cleanup_enabled,
        parent_chat_id=chat.parent_chat_id,
        relation_notes=chat.relation_notes,
        public_link=chat.public_link,
        member_count=member_count,
        has_photo=chat.photo_file_id is not None,
        last_synced_at=chat.last_synced_at,
        created_at=chat.created_at,
    )
