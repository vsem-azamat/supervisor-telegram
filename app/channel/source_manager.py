"""Source manager — DB-backed RSS source registry with health tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import ChannelSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.source_manager")

MAX_ERRORS_BEFORE_DISABLE = 5


async def get_active_sources(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: int,
) -> list[ChannelSource]:
    """Get all enabled sources for a channel, ordered by relevance score descending."""
    async with session_maker() as session:
        result = await session.execute(
            select(ChannelSource)
            .where(
                ChannelSource.channel_id == channel_id,
                ChannelSource.enabled.is_(True),
            )
            .order_by(ChannelSource.relevance_score.desc())
        )
        return list(result.scalars().all())


async def record_fetch_success(
    session_maker: async_sessionmaker[AsyncSession],
    source_url: str,
) -> None:
    """Record a successful fetch for all sources with this URL (may span channels)."""
    async with session_maker() as session:
        result = await session.execute(select(ChannelSource).where(ChannelSource.url == source_url))
        sources = list(result.scalars().all())
        for source in sources:
            source.record_success()
        if sources:
            await session.commit()


async def record_fetch_error(
    session_maker: async_sessionmaker[AsyncSession],
    source_url: str,
    error: str,
) -> None:
    """Record a fetch error for all sources with this URL. Auto-disables after repeated failures."""
    async with session_maker() as session:
        result = await session.execute(select(ChannelSource).where(ChannelSource.url == source_url))
        sources = list(result.scalars().all())
        for source in sources:
            source.record_error(error)
            if not source.enabled:
                logger.warning(
                    "source_auto_disabled",
                    url=source_url,
                    error_count=source.error_count,
                )
        if sources:
            await session.commit()


async def add_source(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: int,
    url: str,
    title: str | None = None,
    added_by: str = "agent",
) -> bool:
    """Add a new source. Returns False if it already exists."""
    async with session_maker() as session:
        existing = await session.execute(
            select(ChannelSource).where(ChannelSource.channel_id == channel_id, ChannelSource.url == url)
        )
        if existing.scalar_one_or_none():
            return False
        source = ChannelSource(
            channel_id=channel_id,
            url=url,
            title=title,
            added_by=added_by,
        )
        session.add(source)
        await session.commit()
        logger.info("source_added", url=url, added_by=added_by)
        return True


async def remove_source(
    session_maker: async_sessionmaker[AsyncSession],
    url: str,
    channel_id: int | None = None,
) -> bool:
    """Remove a source by URL (optionally scoped to channel). Returns True if found and deleted."""
    async with session_maker() as session:
        query = select(ChannelSource).where(ChannelSource.url == url)
        if channel_id:
            query = query.where(ChannelSource.channel_id == channel_id)
        result = await session.execute(query)
        sources = list(result.scalars().all())
        if not sources:
            return False
        for source in sources:
            await session.delete(source)
        await session.commit()
        logger.info("source_removed", url=url, count=len(sources))
        return True


async def seed_sources_from_env(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: int,
    rss_urls: list[str],
) -> int:
    """Seed sources from env config (only adds new ones). Returns count added."""
    added = 0
    for url in rss_urls:
        if await add_source(session_maker, channel_id, url, added_by="config"):
            added += 1
    if added:
        logger.info("sources_seeded", count=added, channel_id=channel_id)
    return added


async def update_source_relevance(
    session_maker: async_sessionmaker[AsyncSession],
    source_urls: list[str],
    *,
    approved: bool,
) -> None:
    """Boost or penalize relevance score for sources based on admin approval."""
    if not source_urls:
        return
    async with session_maker() as session:
        result = await session.execute(select(ChannelSource).where(ChannelSource.url.in_(source_urls)))
        sources = list(result.scalars().all())
        for source in sources:
            if approved:
                source.boost_relevance()
            else:
                source.penalize_relevance()
                if not source.enabled:
                    logger.warning("source_auto_disabled_low_relevance", url=source.url, score=source.relevance_score)
        await session.commit()
