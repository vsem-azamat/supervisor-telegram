"""Tests for schedule_manager — slot computation, schedule/cancel/reschedule posts."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agent.channel.schedule_manager import (
    cancel_scheduled_post,
    get_occupied_slots,
    next_publish_slot,
    reschedule_post,
    schedule_post,
    update_scheduled_text,
)
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.infrastructure.db.models import ChannelPost
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture
def mock_channel() -> MagicMock:
    ch = MagicMock()
    ch.telegram_id = "-1001234567890"
    ch.name = "Test Channel"
    ch.username = "test_channel"
    ch.publish_schedule = ["09:00", "15:00", "21:00"]
    return ch


@pytest.fixture
def mock_telethon() -> AsyncMock:
    tc = AsyncMock()
    tc.is_available = True
    msg_info = MagicMock()
    msg_info.message_id = 42
    msg_info.chat_id = -1001234567890
    msg_info.text = "test"
    msg_info.date = None
    msg_info.sender_id = None
    tc.send_scheduled_message.return_value = msg_info
    tc.send_scheduled_photo.return_value = msg_info
    tc.edit_scheduled_message.return_value = True
    tc.delete_scheduled_messages.return_value = True
    return tc


# ── next_publish_slot tests ──────────────────────────────────────────


class TestNextPublishSlot:
    def test_finds_next_slot_today(self) -> None:
        now = datetime(2026, 3, 7, 8, 0, 0)  # 08:00
        slot = next_publish_slot(["09:00", "15:00", "21:00"], [], now)
        assert slot == datetime(2026, 3, 7, 9, 0, 0)

    def test_skips_past_slots(self) -> None:
        now = datetime(2026, 3, 7, 16, 0, 0)  # 16:00
        slot = next_publish_slot(["09:00", "15:00", "21:00"], [], now)
        assert slot == datetime(2026, 3, 7, 21, 0, 0)

    def test_wraps_to_next_day(self) -> None:
        now = datetime(2026, 3, 7, 22, 0, 0)  # 22:00
        slot = next_publish_slot(["09:00", "15:00", "21:00"], [], now)
        assert slot == datetime(2026, 3, 8, 9, 0, 0)

    def test_avoids_occupied_slots(self) -> None:
        now = datetime(2026, 3, 7, 8, 0, 0)
        occupied = [datetime(2026, 3, 7, 9, 0, 0)]
        slot = next_publish_slot(["09:00", "15:00"], occupied, now)
        assert slot == datetime(2026, 3, 7, 15, 0, 0)

    def test_respects_min_gap(self) -> None:
        now = datetime(2026, 3, 7, 8, 0, 0)
        # Occupied at 8:50, slot at 9:00 — within 30 min gap
        occupied = [datetime(2026, 3, 7, 8, 50, 0)]
        slot = next_publish_slot(["09:00", "15:00"], occupied, now, min_gap_minutes=30)
        assert slot == datetime(2026, 3, 7, 15, 0, 0)

    def test_empty_schedule_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            next_publish_slot([], [], utc_now())

    def test_single_slot_next_day(self) -> None:
        now = datetime(2026, 3, 7, 10, 0, 0)
        slot = next_publish_slot(["09:00"], [], now)
        assert slot == datetime(2026, 3, 8, 9, 0, 0)

    def test_multiple_occupied_same_day(self) -> None:
        now = datetime(2026, 3, 7, 8, 0, 0)
        occupied = [
            datetime(2026, 3, 7, 9, 0, 0),
            datetime(2026, 3, 7, 15, 0, 0),
        ]
        slot = next_publish_slot(["09:00", "15:00", "21:00"], occupied, now)
        assert slot == datetime(2026, 3, 7, 21, 0, 0)


# ── get_occupied_slots tests ─────────────────────────────────────────


class TestGetOccupiedSlots:
    async def test_returns_scheduled_times(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        scheduled_time = utc_now() + timedelta(hours=2)
        async with session_maker() as session:
            post = ChannelPost(channel_id="@test", external_id="e1", title="T", post_text="text")
            post.schedule(scheduled_time, 42)
            session.add(post)
            await session.commit()

        slots = await get_occupied_slots(session_maker, "@test")
        assert len(slots) == 1
        assert slots[0] == scheduled_time

    async def test_ignores_non_scheduled(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        async with session_maker() as session:
            p1 = ChannelPost(channel_id="@test", external_id="e1", title="T", post_text="text")
            p2 = ChannelPost(channel_id="@test", external_id="e2", title="T2", post_text="text2")
            p2.approve(100)
            session.add_all([p1, p2])
            await session.commit()

        slots = await get_occupied_slots(session_maker, "@test")
        assert len(slots) == 0

    async def test_filters_by_channel(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        t = utc_now() + timedelta(hours=2)
        async with session_maker() as session:
            p1 = ChannelPost(channel_id="@ch1", external_id="e1", title="T", post_text="text")
            p1.schedule(t, 42)
            p2 = ChannelPost(channel_id="@ch2", external_id="e2", title="T", post_text="text")
            p2.schedule(t, 43)
            session.add_all([p1, p2])
            await session.commit()

        slots = await get_occupied_slots(session_maker, "@ch1")
        assert len(slots) == 1


# ── schedule_post tests ──────────────────────────────────────────────


class TestSchedulePost:
    async def test_schedule_text_post(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="Hello world")
            session.add(post)
            await session.commit()
            post_id = post.id

        t = utc_now() + timedelta(hours=2)
        result = await schedule_post(mock_telethon, session_maker, post_id, mock_channel, t)
        assert "Scheduled" in result

        mock_telethon.send_scheduled_message.assert_awaited_once()

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
            assert saved.status == PostStatus.SCHEDULED
            assert saved.scheduled_at == t
            assert saved.scheduled_telegram_id == 42

    async def test_schedule_photo_post(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(
                channel_id="-1001234567890",
                external_id="e1",
                title="T",
                post_text="Photo post",
                image_url="https://example.com/img.jpg",
            )
            session.add(post)
            await session.commit()
            post_id = post.id

        t = utc_now() + timedelta(hours=2)
        result = await schedule_post(mock_telethon, session_maker, post_id, mock_channel, t)
        assert "Scheduled" in result
        mock_telethon.send_scheduled_photo.assert_awaited_once()

    async def test_schedule_already_approved(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            post.approve(100)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await schedule_post(mock_telethon, session_maker, post_id, mock_channel, utc_now())
        assert result == "Already published."

    async def test_schedule_already_scheduled(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            post.schedule(utc_now(), 99)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await schedule_post(mock_telethon, session_maker, post_id, mock_channel, utc_now())
        assert result == "Already scheduled."

    async def test_schedule_not_found(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        result = await schedule_post(mock_telethon, session_maker, 999, mock_channel, utc_now())
        assert result == "Post not found."

    async def test_schedule_username_channel_fails(
        self,
        mock_telethon: AsyncMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        ch = MagicMock()
        ch.telegram_id = "@test_channel"

        # Telethon resolves @username to entity with numeric id
        entity = MagicMock()
        entity.id = 123456
        mock_telethon._client = MagicMock()
        mock_telethon._client.get_entity = AsyncMock(return_value=entity)
        mock_telethon.send_scheduled_message = AsyncMock(return_value=MagicMock(message_id=99))

        async with session_maker() as session:
            post = ChannelPost(channel_id="@test_channel", external_id="e1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await schedule_post(mock_telethon, session_maker, post_id, ch, utc_now())
        assert "Scheduled" in result
        mock_telethon._client.get_entity.assert_awaited_once_with("@test_channel")


# ── cancel_scheduled_post tests ──────────────────────────────────────


class TestCancelScheduledPost:
    async def test_cancel_success(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            post.schedule(utc_now() + timedelta(hours=2), 42)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await cancel_scheduled_post(mock_telethon, session_maker, post_id, mock_channel)
        assert "cancelled" in result.lower()

        mock_telethon.delete_scheduled_messages.assert_awaited_once()

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
            assert saved.status == PostStatus.DRAFT
            assert saved.scheduled_at is None
            assert saved.scheduled_telegram_id is None

    async def test_cancel_not_scheduled(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await cancel_scheduled_post(mock_telethon, session_maker, post_id, mock_channel)
        assert "not scheduled" in result.lower()


# ── reschedule_post tests ────────────────────────────────────────────


class TestReschedulePost:
    async def test_reschedule_success(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        old_time = utc_now() + timedelta(hours=2)
        new_time = utc_now() + timedelta(hours=5)

        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            post.schedule(old_time, 10)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await reschedule_post(mock_telethon, session_maker, post_id, mock_channel, new_time)
        assert "Rescheduled" in result

        mock_telethon.delete_scheduled_messages.assert_awaited_once()
        mock_telethon.send_scheduled_message.assert_awaited_once()

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
            assert saved.status == PostStatus.SCHEDULED
            assert saved.scheduled_at == new_time
            assert saved.scheduled_telegram_id == 42

    async def test_reschedule_not_scheduled(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await reschedule_post(mock_telethon, session_maker, post_id, mock_channel, utc_now())
        assert "not scheduled" in result.lower()

    async def test_reschedule_telethon_fails_reverts_to_draft(
        self,
        mock_telethon: AsyncMock,
        mock_channel: MagicMock,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        mock_telethon.send_scheduled_message.return_value = None

        async with session_maker() as session:
            post = ChannelPost(channel_id="-1001234567890", external_id="e1", title="T", post_text="text")
            post.schedule(utc_now() + timedelta(hours=2), 10)
            session.add(post)
            await session.commit()
            post_id = post.id

        result = await reschedule_post(mock_telethon, session_maker, post_id, mock_channel, utc_now())
        assert "failed" in result.lower()

        async with session_maker() as session:
            saved = (await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
            assert saved.status == PostStatus.DRAFT


# ── update_scheduled_text tests ──────────────────────────────────────


class TestUpdateScheduledText:
    async def test_updates_scheduled_message(self, mock_telethon: AsyncMock, mock_channel: MagicMock) -> None:
        post = MagicMock()
        post.status = PostStatus.SCHEDULED
        post.scheduled_telegram_id = 42
        post.post_text = "Updated text"

        result = await update_scheduled_text(mock_telethon, mock_channel, post)
        assert result is True
        mock_telethon.edit_scheduled_message.assert_awaited_once()

    async def test_skips_non_scheduled(self, mock_telethon: AsyncMock, mock_channel: MagicMock) -> None:
        post = MagicMock()
        post.status = PostStatus.DRAFT
        post.scheduled_telegram_id = None

        result = await update_scheduled_text(mock_telethon, mock_channel, post)
        assert result is False
        mock_telethon.edit_scheduled_message.assert_not_awaited()
