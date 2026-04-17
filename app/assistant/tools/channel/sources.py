"""RSS source tools: get / add / remove."""

from __future__ import annotations

from typing import TYPE_CHECKING

# RunContext + AssistantDeps kept at runtime — PydanticAI's @agent.tool
# decorator resolves tool-function type hints at registration time.
from pydantic_ai import RunContext  # noqa: TC002

from app.assistant.agent import AssistantDeps, _validate_channel_id  # noqa: TC001
from app.core.logging import get_logger

if TYPE_CHECKING:
    from pydantic_ai import Agent

logger = get_logger("assistant.tools.channel.sources")


def register_sources_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register RSS source tools on the agent."""

    @agent.tool
    async def get_sources(ctx: RunContext[AssistantDeps], channel_id: int) -> str:
        """List RSS sources for a channel. Use list_channels first if unsure about channel_id."""
        from sqlalchemy import select

        from app.db.models import ChannelSource

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelSource).where(ChannelSource.channel_id == channel_id))
            sources = result.scalars().all()

        if not sources:
            return f"No sources found for {channel_id}."

        lines = [f"Sources for {channel_id} ({len(sources)} total):\n"]
        for s in sources:
            status = "on" if s.enabled else "OFF"
            lines.append(f"- [{status}] {s.title or s.url[:40]} (score: {s.relevance_score:.1f})")
        return "\n".join(lines)

    @agent.tool
    async def add_source(ctx: RunContext[AssistantDeps], url: str, channel_id: int, title: str = "") -> str:
        """Add a new RSS source for a channel."""
        error = await _validate_channel_id(ctx, channel_id)
        if error:
            return error

        from sqlalchemy import select

        from app.db.models import ChannelSource

        try:
            async with ctx.deps.session_maker() as session:
                existing = await session.execute(
                    select(ChannelSource).where(ChannelSource.channel_id == channel_id, ChannelSource.url == url)
                )
                if existing.scalar_one_or_none():
                    return f"Source already exists for {channel_id}: {url}"

                source = ChannelSource(
                    channel_id=channel_id,
                    url=url,
                    source_type="rss",
                    title=title or None,
                    added_by="assistant",
                )
                session.add(source)
                await session.commit()
            return f"Added source: {url} for {channel_id}"
        except Exception:
            logger.exception("add_source_failed", url=url, channel_id=channel_id)
            return "Не удалось добавить источник. Проверьте логи бота."

    @agent.tool
    async def remove_source(ctx: RunContext[AssistantDeps], url: str, channel_id: int) -> str:
        """Remove an RSS source by URL for a specific channel. channel_id is required."""
        from sqlalchemy import select

        from app.db.models import ChannelSource

        try:
            async with ctx.deps.session_maker() as session:
                result = await session.execute(
                    select(ChannelSource).where(ChannelSource.channel_id == channel_id, ChannelSource.url == url)
                )
                source = result.scalar_one_or_none()
                if not source:
                    return f"Source not found: {url} for {channel_id}"
                await session.delete(source)
                await session.commit()
            return f"Removed source: {url}"
        except Exception:
            logger.exception("remove_source_failed", url=url)
            return "Не удалось удалить источник. Проверьте логи бота."
