"""Scheduling tools: posting schedule, per-post schedule/reschedule/cancel, publish schedule."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

# RunContext + AssistantDeps kept at runtime — PydanticAI's @agent.tool
# decorator resolves tool-function type hints at registration time.
from pydantic_ai import RunContext  # noqa: TC002

from app.assistant.agent import AssistantDeps  # noqa: TC001

if TYPE_CHECKING:
    from pydantic_ai import Agent

_SCHEDULE_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def register_schedule_tools(agent: Agent[AssistantDeps, str]) -> None:
    """Register scheduling tools on the agent."""

    @agent.tool
    async def set_schedule(ctx: RunContext[AssistantDeps], schedule: str, channel_id: int = 0) -> str:
        """Set posting schedule. Format: comma-separated HH:MM times in UTC, e.g. '09:00,15:00,21:00'. Persists to DB."""
        times = [t.strip() for t in schedule.split(",") if t.strip()]
        for t in times:
            if not _SCHEDULE_TIME_RE.match(t):
                return f"Неверный формат времени: {t}. Используйте HH:MM (00:00-23:59)."

        from app.channel.channel_repo import get_active_channels, update_channel

        if channel_id:
            ch = await update_channel(ctx.deps.session_maker, channel_id, posting_schedule=times)
            if not ch:
                return f"Канал {channel_id} не найден."
            updated = 1
        else:
            channels = await get_active_channels(ctx.deps.session_maker)
            updated = 0
            for ch in channels:
                await update_channel(ctx.deps.session_maker, ch.telegram_id, posting_schedule=times)
                updated += 1

        orch = ctx.deps.channel_orchestrator
        if orch:
            targets = orch.orchestrators
            if channel_id:
                targets = [o for o in targets if o.channel_id == channel_id]
            for o in targets:
                o.channel.posting_schedule = times

        return f"Расписание обновлено: {times} для {updated} канал(ов). Сохранено в БД."

    @agent.tool
    async def list_scheduled(ctx: RunContext[AssistantDeps], channel_id: int = 0) -> str:
        """List all currently scheduled (not yet published) posts. Leave channel_id empty for all channels."""
        from sqlalchemy import select

        from app.infrastructure.db.models import ChannelPost

        query = select(ChannelPost).where(ChannelPost.status == "scheduled").order_by(ChannelPost.scheduled_at)
        if channel_id:
            query = query.where(ChannelPost.channel_id == channel_id)

        async with ctx.deps.session_maker() as session:
            result = await session.execute(query)
            posts = result.scalars().all()

        if not posts:
            return "Нет запланированных постов."

        lines = [f"Scheduled posts ({len(posts)}):\n"]
        for p in posts:
            time_str = p.scheduled_at.strftime("%d %b %H:%M UTC") if p.scheduled_at else "?"
            lines.append(f"- #{p.id} [{p.channel_id}] {time_str}: {p.title[:50]}")
        return "\n".join(lines)

    @agent.tool
    async def schedule_post_tool(
        ctx: RunContext[AssistantDeps],
        post_id: int,
        time: str = "",
    ) -> str:
        """Schedule a draft post for future delivery. time format: 'YYYY-MM-DD HH:MM' UTC, or empty for next available slot. IMPORTANT: Ask for confirmation first."""
        from datetime import datetime as dt

        from sqlalchemy import select

        from app.infrastructure.db.models import Channel, ChannelPost

        tc = ctx.deps.telethon
        assert tc is not None  # guaranteed by prepare_tools

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()

        if not post:
            return "Post not found."

        async with ctx.deps.session_maker() as session:
            ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            return f"Channel {post.channel_id} not found."

        if time:
            try:
                publish_time = dt.strptime(time, "%Y-%m-%d %H:%M")
            except ValueError:
                return "Invalid time format. Use 'YYYY-MM-DD HH:MM' UTC."
        elif channel.publish_schedule:
            from app.channel.schedule_manager import get_occupied_slots, next_publish_slot

            occupied = await get_occupied_slots(ctx.deps.session_maker, channel.telegram_id)
            try:
                publish_time = next_publish_slot(channel.publish_schedule, occupied)
            except ValueError:
                return "No available publish slots."
        else:
            return "No time specified and no publish_schedule configured for this channel."

        from app.channel.schedule_manager import schedule_post

        return await schedule_post(tc, ctx.deps.session_maker, post_id, channel, publish_time)

    @agent.tool
    async def reschedule_post_tool(
        ctx: RunContext[AssistantDeps],
        post_id: int,
        new_time: str,
    ) -> str:
        """Reschedule an already-scheduled post. Format: 'YYYY-MM-DD HH:MM' UTC."""
        from datetime import datetime as dt

        from sqlalchemy import select

        from app.infrastructure.db.models import Channel, ChannelPost

        tc = ctx.deps.telethon
        assert tc is not None  # guaranteed by prepare_tools

        try:
            publish_time = dt.strptime(new_time, "%Y-%m-%d %H:%M")
        except ValueError:
            return "Invalid time format. Use 'YYYY-MM-DD HH:MM' UTC."

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()

        if not post:
            return "Post not found."

        async with ctx.deps.session_maker() as session:
            ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            return f"Channel {post.channel_id} not found."

        from app.channel.schedule_manager import reschedule_post

        return await reschedule_post(tc, ctx.deps.session_maker, post_id, channel, publish_time)

    @agent.tool
    async def cancel_scheduled_post_tool(ctx: RunContext[AssistantDeps], post_id: int) -> str:
        """Cancel a scheduled post — removes from Telegram queue, reverts to draft."""
        from sqlalchemy import select

        from app.infrastructure.db.models import Channel, ChannelPost

        tc = ctx.deps.telethon
        assert tc is not None  # guaranteed by prepare_tools

        async with ctx.deps.session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = result.scalar_one_or_none()

        if not post:
            return "Post not found."

        async with ctx.deps.session_maker() as session:
            ch_result = await session.execute(select(Channel).where(Channel.telegram_id == post.channel_id))
            channel = ch_result.scalar_one_or_none()

        if not channel:
            return f"Channel {post.channel_id} not found."

        from app.channel.schedule_manager import cancel_scheduled_post

        return await cancel_scheduled_post(tc, ctx.deps.session_maker, post_id, channel)

    @agent.tool
    async def set_publish_schedule(
        ctx: RunContext[AssistantDeps],
        channel_id: int,
        schedule: str,
    ) -> str:
        """Set when approved posts go live. Format: comma-separated HH:MM UTC, e.g. '09:00,13:00,18:00'. Empty string disables scheduling (posts publish immediately on approve)."""
        from app.channel.channel_repo import update_channel

        times = [t.strip() for t in schedule.split(",") if t.strip()] if schedule else []
        for t in times:
            if not _SCHEDULE_TIME_RE.match(t):
                return f"Invalid time format: {t}. Use HH:MM (00:00-23:59)."

        ch = await update_channel(ctx.deps.session_maker, channel_id, publish_schedule=times or None)
        if not ch:
            return f"Channel {channel_id} not found."

        if times:
            return f"Publish schedule set: {times} for {channel_id}. Approved posts will be scheduled."
        return f"Publish schedule cleared for {channel_id}. Posts will publish immediately on approve."
