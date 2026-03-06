"""Channel statistics queries for the webapp API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select

from app.infrastructure.db.models import ChannelPost, ChannelSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_channel_stats(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
) -> dict[str, Any]:
    """Aggregate statistics for a single channel."""
    async with session_maker() as session:
        # Post counts by status
        post_q = select(
            func.count().label("total"),
            func.count(case((ChannelPost.status == "approved", 1))).label("approved"),
            func.count(case((ChannelPost.status == "rejected", 1))).label("rejected"),
            func.count(case((ChannelPost.status == "draft", 1))).label("draft"),
        ).where(ChannelPost.channel_id == channel_id)
        post_row = (await session.execute(post_q)).one()

        total = post_row.total or 0
        approved = post_row.approved or 0
        rejected = post_row.rejected or 0
        draft = post_row.draft or 0
        approval_rate = round(approved / total, 4) if total else 0.0

        # Source counts
        src_q = select(
            func.count().label("total"),
            func.count(case((ChannelSource.enabled.is_(True), 1))).label("active"),
            func.count(case((ChannelSource.enabled.is_(False), 1))).label("disabled"),
            func.coalesce(func.avg(ChannelSource.relevance_score), 0.0).label("avg_relevance"),
        ).where(ChannelSource.channel_id == channel_id)
        src_row = (await session.execute(src_q)).one()

        return {
            "channel_id": channel_id,
            "total_posts": total,
            "approved": approved,
            "rejected": rejected,
            "draft": draft,
            "approval_rate": approval_rate,
            "active_sources": src_row.active or 0,
            "disabled_sources": src_row.disabled or 0,
            "avg_relevance_score": round(float(src_row.avg_relevance), 4),
        }


async def get_all_channels_stats(
    session_maker: async_sessionmaker[AsyncSession],
) -> list[dict[str, Any]]:
    """Return stats for every known channel (union of posts + sources)."""
    async with session_maker() as session:
        # Distinct channel_ids
        ch_q = select(ChannelPost.channel_id).union(select(ChannelSource.channel_id))
        rows = (await session.execute(ch_q)).all()

    channel_ids: list[str] = [r[0] for r in rows]
    results: list[dict[str, Any]] = []
    for cid in sorted(channel_ids):
        results.append(await get_channel_stats(session_maker, cid))
    return results


async def get_recent_posts(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return most recent posts for a channel."""
    async with session_maker() as session:
        q = (
            select(ChannelPost)
            .where(ChannelPost.channel_id == channel_id)
            .order_by(ChannelPost.created_at.desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).scalars().all()

        return [
            {
                "id": p.id,
                "external_id": p.external_id,
                "title": p.title,
                "status": p.status,
                "source_url": p.source_url,
                "telegram_message_id": p.telegram_message_id,
                "admin_feedback": p.admin_feedback,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ]


async def get_sources(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
) -> list[dict[str, Any]]:
    """Return all sources for a channel."""
    async with session_maker() as session:
        q = (
            select(ChannelSource)
            .where(ChannelSource.channel_id == channel_id)
            .order_by(ChannelSource.relevance_score.desc())
        )
        rows = (await session.execute(q)).scalars().all()

        return [
            {
                "id": s.id,
                "url": s.url,
                "source_type": s.source_type,
                "title": s.title,
                "language": s.language,
                "enabled": s.enabled,
                "relevance_score": s.relevance_score,
                "error_count": s.error_count,
                "last_error": s.last_error,
                "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ]
