"""Schedule manager — computes publish slots and manages Telegram scheduled messages."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.core.time import utc_now
from app.domain.value_objects import PostStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.infrastructure.db.models import Channel, ChannelPost
    from app.infrastructure.telegram.telethon_client import TelethonClient

logger = get_logger("channel.schedule_manager")


def next_publish_slot(
    publish_schedule: list[str],
    occupied_slots: list[datetime],
    now: datetime | None = None,
    min_gap_minutes: int = 30,
) -> datetime:
    """Find the next available publish slot.

    Args:
        publish_schedule: List of "HH:MM" UTC strings.
        occupied_slots: Already-scheduled datetimes.
        now: Current time (defaults to utc_now()).
        min_gap_minutes: Minimum gap between posts in same slot.

    Returns:
        Next available naive UTC datetime.
    """
    if not publish_schedule:
        msg = "publish_schedule must not be empty"
        raise ValueError(msg)

    now = now or utc_now()

    parsed: list[tuple[int, int]] = []
    for entry in publish_schedule:
        parts = entry.strip().split(":")
        if len(parts) == 2:
            parsed.append((int(parts[0]), int(parts[1])))
    parsed.sort()

    if not parsed:
        msg = "No valid times in publish_schedule"
        raise ValueError(msg)

    # Try today and next 7 days
    for day_offset in range(8):
        base = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
        for hour, minute in parsed:
            candidate = base.replace(hour=hour, minute=minute)

            # Must be in the future (at least 60s ahead)
            if candidate <= now + timedelta(seconds=60):
                continue

            # Check no occupied slot within min_gap_minutes
            conflict = False
            for occ in occupied_slots:
                if abs((candidate - occ).total_seconds()) < min_gap_minutes * 60:
                    conflict = True
                    break
            if not conflict:
                return candidate

    # Fallback: first slot tomorrow
    base = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return base.replace(hour=parsed[0][0], minute=parsed[0][1])


async def get_occupied_slots(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: str,
) -> list[datetime]:
    """Query DB for all SCHEDULED posts' scheduled_at times for a channel."""
    from sqlalchemy import select

    from app.infrastructure.db.models import ChannelPost

    async with session_maker() as session:
        result = await session.execute(
            select(ChannelPost.scheduled_at).where(
                ChannelPost.channel_id == channel_id,
                ChannelPost.status == PostStatus.SCHEDULED,
                ChannelPost.scheduled_at.is_not(None),
            )
        )
        return [row[0] for row in result.all() if row[0] is not None]


def _resolve_chat_id(channel: Channel) -> int:
    """Get numeric chat ID from channel telegram_id."""
    tid = channel.telegram_id
    if tid.startswith("@"):
        # For @username channels, we need the numeric ID
        # The caller should provide the numeric ID via channel lookup
        msg = f"Cannot resolve @username to numeric ID for scheduling: {tid}"
        raise ValueError(msg)
    return int(tid)


async def schedule_post(
    telethon_client: TelethonClient,
    session_maker: async_sessionmaker[AsyncSession],
    post_id: int,
    channel: Channel,
    publish_time: datetime,
) -> str:
    """Schedule a post for future delivery via Telethon. Returns status message."""
    from sqlalchemy import select

    from app.infrastructure.db.models import ChannelPost

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post: ChannelPost | None = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status == PostStatus.APPROVED:
            return "Already published."
        if post.status == PostStatus.SCHEDULED:
            return "Already scheduled."

        try:
            chat_id = _resolve_chat_id(channel)
        except ValueError:
            return f"Cannot schedule: channel {channel.telegram_id} needs a numeric ID."

        # Send as scheduled message via Telethon (Markdown for formatting)
        if post.image_url:
            msg_info = await telethon_client.send_scheduled_photo(
                chat_id=chat_id,
                photo=post.image_url,
                caption=post.post_text[:1024],
                schedule_date=publish_time,
                parse_mode="md",
            )
        else:
            msg_info = await telethon_client.send_scheduled_message(
                chat_id=chat_id,
                text=post.post_text,
                schedule_date=publish_time,
                parse_mode="md",
            )

        if not msg_info:
            return "Failed to schedule: Telethon client unavailable."

        post.schedule(publish_time, msg_info.message_id)
        await session.commit()

        time_str = publish_time.strftime("%d %b %H:%M UTC")
        logger.info(
            "post_scheduled",
            post_id=post_id,
            scheduled_at=time_str,
            telegram_id=msg_info.message_id,
        )
        return f"Scheduled for {time_str} (msg #{msg_info.message_id})"


async def cancel_scheduled_post(
    telethon_client: TelethonClient,
    session_maker: async_sessionmaker[AsyncSession],
    post_id: int,
    channel: Channel,
) -> str:
    """Cancel a scheduled post — delete from Telegram and revert to DRAFT."""
    from sqlalchemy import select

    from app.infrastructure.db.models import ChannelPost

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post: ChannelPost | None = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status != PostStatus.SCHEDULED:
            return f"Post is not scheduled (status: {post.status})."

        # Delete from Telegram
        if post.scheduled_telegram_id:
            try:
                chat_id = _resolve_chat_id(channel)
                await telethon_client.delete_scheduled_messages(
                    chat_id,
                    [post.scheduled_telegram_id],
                )
            except Exception:
                logger.warning("cancel_telegram_delete_failed", post_id=post_id, exc_info=True)

        post.unschedule()
        await session.commit()
        logger.info("post_schedule_cancelled", post_id=post_id)
        return "Schedule cancelled. Post reverted to draft."


async def reschedule_post(
    telethon_client: TelethonClient,
    session_maker: async_sessionmaker[AsyncSession],
    post_id: int,
    channel: Channel,
    new_time: datetime,
) -> str:
    """Reschedule: delete old scheduled message, create new one."""
    from sqlalchemy import select

    from app.infrastructure.db.models import ChannelPost

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        post: ChannelPost | None = result.scalar_one_or_none()
        if not post:
            return "Post not found."
        if post.status != PostStatus.SCHEDULED:
            return f"Post is not scheduled (status: {post.status})."

        try:
            chat_id = _resolve_chat_id(channel)
        except ValueError:
            return f"Cannot reschedule: channel {channel.telegram_id} needs a numeric ID."

        # Delete old scheduled message
        if post.scheduled_telegram_id:
            await telethon_client.delete_scheduled_messages(
                chat_id,
                [post.scheduled_telegram_id],
            )

        # Create new scheduled message (Markdown for formatting)
        if post.image_url:
            msg_info = await telethon_client.send_scheduled_photo(
                chat_id=chat_id,
                photo=post.image_url,
                caption=post.post_text[:1024],
                schedule_date=new_time,
                parse_mode="md",
            )
        else:
            msg_info = await telethon_client.send_scheduled_message(
                chat_id=chat_id,
                text=post.post_text,
                schedule_date=new_time,
                parse_mode="md",
            )

        if not msg_info:
            post.unschedule()
            await session.commit()
            return "Reschedule failed: could not create new scheduled message. Post reverted to draft."

        post.reschedule(new_time, msg_info.message_id)
        await session.commit()

        time_str = new_time.strftime("%d %b %H:%M UTC")
        logger.info("post_rescheduled", post_id=post_id, new_time=time_str)
        return f"Rescheduled for {time_str}"


async def update_scheduled_text(
    telethon_client: TelethonClient,
    channel: Channel,
    post: ChannelPost,
) -> bool:
    """Update the text of an already-scheduled Telegram message. Returns True on success."""
    if post.status != PostStatus.SCHEDULED or not post.scheduled_telegram_id:
        return False

    try:
        chat_id = _resolve_chat_id(channel)
    except ValueError:
        return False

    return await telethon_client.edit_scheduled_message(
        chat_id=chat_id,
        message_id=post.scheduled_telegram_id,
        text=post.post_text,
    )
