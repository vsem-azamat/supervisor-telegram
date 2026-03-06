"""Source manager — DB-backed RSS source registry with health tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.infrastructure.db.models import ChannelSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.source_manager")

MAX_ERRORS_BEFORE_DISABLE = 5


async def get_active_sources(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
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
    """Record a successful fetch for a source."""
    async with session_maker() as session:
        result = await session.execute(select(ChannelSource).where(ChannelSource.url == source_url))
        source = result.scalar_one_or_none()
        if source:
            source.record_success()
            await session.commit()


async def record_fetch_error(
    session_maker: async_sessionmaker[AsyncSession],
    source_url: str,
    error: str,
) -> None:
    """Record a fetch error. Auto-disables after repeated failures."""
    async with session_maker() as session:
        result = await session.execute(select(ChannelSource).where(ChannelSource.url == source_url))
        source = result.scalar_one_or_none()
        if source:
            source.record_error(error)
            if not source.enabled:
                logger.warning(
                    "source_auto_disabled",
                    url=source_url,
                    error_count=source.error_count,
                )
            await session.commit()


async def add_source(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
    url: str,
    title: str | None = None,
    added_by: str = "agent",
) -> bool:
    """Add a new source. Returns False if it already exists."""
    async with session_maker() as session:
        existing = await session.execute(select(ChannelSource).where(ChannelSource.url == url))
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
) -> bool:
    """Remove a source by URL. Returns True if found and deleted."""
    async with session_maker() as session:
        result = await session.execute(select(ChannelSource).where(ChannelSource.url == url))
        source = result.scalar_one_or_none()
        if not source:
            return False
        await session.delete(source)
        await session.commit()
        logger.info("source_removed", url=url)
        return True


async def seed_sources_from_env(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
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
        for url in source_urls:
            result = await session.execute(select(ChannelSource).where(ChannelSource.url == url))
            source = result.scalar_one_or_none()
            if not source:
                continue
            if approved:
                source.boost_relevance()
            else:
                source.penalize_relevance()
                if not source.enabled:
                    logger.warning("source_auto_disabled_low_relevance", url=url, score=source.relevance_score)
        await session.commit()
