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
from app.db.models import Channel, ChannelPost
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import (
    DraftBucket,
    HomeStats,
    ScheduledPostEntry,
    SessionCostSummary,
)

router = APIRouter(prefix="/stats", tags=["stats"])

_SCHEDULED_WINDOW_HOURS = 24


@router.get("/home", response_model=HomeStats)
async def home_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
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

    return HomeStats(
        drafts=drafts,
        scheduled_next_24h=scheduled,
        session_cost=SessionCostSummary.from_tracker(get_session_summary()),
    )
