"""Home dashboard aggregator."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.cost_tracker import get_session_summary
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import Channel, ChannelPost, Chat, ChatMemberSnapshot, Message
from app.webapi.deps import get_session, get_telethon_stats, require_super_admin
from app.webapi.schemas import (
    ChatHeatmapSummary,
    DraftBucket,
    HomeStats,
    MembersDeltaEntry,
    PostViewsEntry,
    ScheduledPostEntry,
    SessionCostSummary,
)
from app.webapi.services.telethon_stats import TelethonStatsService

router = APIRouter(prefix="/stats", tags=["stats"])

_SCHEDULED_WINDOW_HOURS = 24
_POST_VIEWS_TOP_N = 5
_POST_VIEWS_LOOKBACK_DAYS = 7
_CHAT_HEATMAP_TOP_N = 8
_CHAT_HEATMAP_LOOKBACK_DAYS = 7


async def _compute_members_delta(session: AsyncSession, now: datetime.datetime) -> list[MembersDeltaEntry]:
    """For every chat with ≥1 snapshot: current count + Δ over 24h / 7d.

    Baseline = oldest snapshot whose captured_at <= (now - window). If none,
    delta is None. This is cheaper than per-chat queries because we fetch all
    relevant snapshots once and bucket in Python.
    """
    lookback_7d = now - datetime.timedelta(days=7)
    rows = (
        await session.execute(
            select(ChatMemberSnapshot, Chat.title)
            .join(Chat, Chat.id == ChatMemberSnapshot.chat_id, isouter=True)
            .where(ChatMemberSnapshot.captured_at >= lookback_7d)
            .order_by(ChatMemberSnapshot.captured_at.asc())
        )
    ).all()
    by_chat: dict[int, list[tuple[datetime.datetime, int, str | None]]] = {}
    for snap, title in rows:
        by_chat.setdefault(snap.chat_id, []).append((snap.captured_at, snap.member_count, title))

    out: list[MembersDeltaEntry] = []
    for chat_id, points in by_chat.items():
        if not points:
            continue
        title = points[-1][2]
        current = points[-1][1]
        baseline_24h = next(
            (c for ts, c, _ in points if ts <= now - datetime.timedelta(hours=24)),
            None,
        )
        baseline_7d = next(
            (c for ts, c, _ in points if ts <= now - datetime.timedelta(days=7)),
            None,
        )
        out.append(
            MembersDeltaEntry(
                chat_id=chat_id,
                title=title,
                current=current,
                delta_24h=(current - baseline_24h) if baseline_24h is not None else None,
                delta_7d=(current - baseline_7d) if baseline_7d is not None else None,
            )
        )
    return out


@router.get("/home", response_model=HomeStats)
async def home_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    stats_svc: Annotated[TelethonStatsService, Depends(get_telethon_stats)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> HomeStats:
    draft_count = func.count(ChannelPost.id).label("draft_count")
    drafts_rows = (
        await session.execute(
            select(
                ChannelPost.channel_id,
                Channel.name,
                draft_count,
            )
            .join(Channel, Channel.telegram_id == ChannelPost.channel_id, isouter=True)
            .where(ChannelPost.status == PostStatus.DRAFT)
            .group_by(ChannelPost.channel_id, Channel.name)
            .order_by(draft_count.desc())
        )
    ).all()
    drafts = [
        DraftBucket(
            channel_id=row.channel_id,
            channel_name=row.name or f"#{row.channel_id}",
            count=int(row.draft_count),
        )
        for row in drafts_rows
    ]

    now = utc_now()
    horizon = now + datetime.timedelta(hours=_SCHEDULED_WINDOW_HOURS)
    scheduled_rows = (
        await session.execute(
            select(ChannelPost, Channel.name)
            .join(Channel, Channel.telegram_id == ChannelPost.channel_id, isouter=True)
            .where(ChannelPost.scheduled_at.is_not(None))
            .where(ChannelPost.scheduled_at >= now)
            .where(ChannelPost.scheduled_at <= horizon)
            .order_by(ChannelPost.scheduled_at.asc())
        )
    ).all()
    scheduled = [
        ScheduledPostEntry(
            post_id=post.id,
            channel_id=post.channel_id,
            channel_name=ch_name or f"#{post.channel_id}",
            title=post.title,
            scheduled_at=post.scheduled_at,
        )
        for post, ch_name in scheduled_rows
    ]

    # --- Post views (last N published posts, enriched via Telethon) ---
    views_lookback = now - datetime.timedelta(days=_POST_VIEWS_LOOKBACK_DAYS)
    published_rows = (
        await session.execute(
            select(ChannelPost, Channel.name)
            .join(Channel, Channel.telegram_id == ChannelPost.channel_id, isouter=True)
            .where(ChannelPost.status == PostStatus.APPROVED)
            .where(ChannelPost.published_at.is_not(None))
            .where(ChannelPost.published_at >= views_lookback)
            .where(ChannelPost.telegram_message_id.is_not(None))
            .order_by(ChannelPost.published_at.desc())
            .limit(_POST_VIEWS_TOP_N)
        )
    ).all()

    # Group message IDs by channel to batch Telethon calls.
    views_by_channel: dict[int, dict[int, int]] = {}
    channel_to_msgs: dict[int, list[int]] = {}
    for post, _name in published_rows:
        channel_to_msgs.setdefault(post.channel_id, []).append(post.telegram_message_id)
    for ch_id, msg_ids in channel_to_msgs.items():
        views_by_channel[ch_id] = await stats_svc.get_post_views_batch(ch_id, msg_ids)

    post_views = [
        PostViewsEntry(
            post_id=post.id,
            channel_id=post.channel_id,
            channel_name=ch_name or f"#{post.channel_id}",
            title=post.title,
            published_at=post.published_at,
            views=views_by_channel.get(post.channel_id, {}).get(post.telegram_message_id, 0),
        )
        for post, ch_name in published_rows
    ]

    # --- Chat heatmap summary (top N chats by total messages, last 7d) ---
    heatmap_since = now - datetime.timedelta(days=_CHAT_HEATMAP_LOOKBACK_DAYS)
    total_msgs = func.count(Message.id).label("total_msgs")
    heatmap_rows = (
        await session.execute(
            select(Message.chat_id, Chat.title, total_msgs)
            .join(Chat, Chat.id == Message.chat_id, isouter=True)
            .where(Message.timestamp >= heatmap_since)
            .group_by(Message.chat_id, Chat.title)
            .order_by(total_msgs.desc())
            .limit(_CHAT_HEATMAP_TOP_N)
        )
    ).all()
    chat_heatmap = [
        ChatHeatmapSummary(chat_id=row.chat_id, title=row.title, total_messages=int(row.total_msgs))
        for row in heatmap_rows
    ]

    # --- Members delta ---
    members_delta = await _compute_members_delta(session, now)

    return HomeStats(
        drafts=drafts,
        scheduled_next_24h=scheduled,
        session_cost=SessionCostSummary.from_tracker(get_session_summary()),
        post_views=post_views,
        chat_heatmap=chat_heatmap,
        members_delta=members_delta,
    )
