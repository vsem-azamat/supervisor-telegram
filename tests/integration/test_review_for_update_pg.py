"""Integration tests for review service FOR UPDATE concurrency.

Closes the gap where SQLite silently ignores `.with_for_update()` — these
tests verify that concurrent review actions against the same ChannelPost
serialize correctly against real Postgres, and that the atomic
UPDATE ... RETURNING slot-reservation in `try_reserve_daily_slot` actually
enforces the daily limit under concurrent approves.

LLM and Telegram sends are mocked (no publish_fn side effects hit the
network). Everything else runs against a real Postgres database.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from app.channel.channel_repo import try_reserve_daily_slot
from app.channel.review.service import approve_post, delete_post, reject_post
from app.channel.schedule_manager import schedule_post
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import Channel, ChannelPost
from sqlalchemy import select

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CHANNEL_TG_ID = -100123456789


async def _insert_channel(session_maker, *, max_posts_per_day: int = 3, daily_count: int = 0) -> int:
    """Insert a Channel row with a configurable daily-post budget. Returns PK id."""
    async with session_maker() as session:
        channel = Channel(telegram_id=_CHANNEL_TG_ID, name="Test")
        channel.max_posts_per_day = max_posts_per_day
        channel.daily_posts_count = daily_count
        channel.daily_count_date = utc_now().strftime("%Y-%m-%d")
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        return channel.id


async def _insert_post(session_maker, *, status: str = PostStatus.DRAFT, external_id: str = "p1") -> int:
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=_CHANNEL_TG_ID,
            external_id=external_id,
            title="Test post",
            post_text="Body of the post",
        )
        post.status = status
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


async def _read_post(session_maker, post_id: int) -> ChannelPost:
    async with session_maker() as session:
        result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
        return result.scalar_one()


class TestConcurrentReviewActions:
    """Concurrent review actions on the same post must serialize via FOR UPDATE."""

    async def test_concurrent_approve_and_reject_yields_single_winner(self, pg_session_maker):
        """approve + reject fired together — exactly one wins, the other sees the winner."""
        await _insert_channel(pg_session_maker, max_posts_per_day=5)
        post_id = await _insert_post(pg_session_maker)

        publish_fn = AsyncMock(return_value=42)

        approve_task = asyncio.create_task(approve_post(post_id, _CHANNEL_TG_ID, publish_fn, pg_session_maker))
        reject_task = asyncio.create_task(reject_post(post_id, pg_session_maker, reason="race"))

        (approve_msg, _), reject_msg = await asyncio.gather(approve_task, reject_task)

        final = await _read_post(pg_session_maker, post_id)

        # Exactly one transition committed, the other saw the final state.
        assert final.status in (PostStatus.APPROVED, PostStatus.REJECTED)
        if final.status == PostStatus.APPROVED:
            assert reject_msg == "Already published — cannot reject."
        else:
            assert (
                "Failed to publish" in approve_msg
                or "Already rejected" in approve_msg
                or (approve_msg.startswith("Published") is False)
            )

    async def test_double_approve_is_idempotent(self, pg_session_maker):
        """Two concurrent approves on same post — only one publishes."""
        await _insert_channel(pg_session_maker, max_posts_per_day=5)
        post_id = await _insert_post(pg_session_maker)

        publish_fn = AsyncMock(return_value=99)

        t1 = asyncio.create_task(approve_post(post_id, _CHANNEL_TG_ID, publish_fn, pg_session_maker))
        t2 = asyncio.create_task(approve_post(post_id, _CHANNEL_TG_ID, publish_fn, pg_session_maker))
        (m1, id1), (m2, id2) = await asyncio.gather(t1, t2)

        # Exactly one published.
        published_count = sum(1 for msg in (m1, m2) if msg.startswith("Published"))
        already_count = sum(1 for msg in (m1, m2) if msg == "Already published.")
        assert published_count == 1, f"expected 1 publish, got messages: {m1!r} / {m2!r}"
        assert already_count == 1, f"expected 1 'already published', got: {m1!r} / {m2!r}"
        # publish_fn called at most once thanks to FOR UPDATE + status check
        assert publish_fn.call_count == 1

        final = await _read_post(pg_session_maker, post_id)
        assert final.status == PostStatus.APPROVED
        assert final.telegram_message_id == 99

    async def test_delete_vs_approve_serializes(self, pg_session_maker):
        """delete + approve fired together — FOR UPDATE serializes them, both complete.

        Note: `approve_post` has no SKIPPED/REJECTED guard today, so when delete
        wins the lock first, approve still publishes. This test pins the
        serialization invariant (two real transactions, no deadlock) without
        asserting on which one wins — revisit if the status guards are tightened.
        """
        await _insert_channel(pg_session_maker, max_posts_per_day=5)
        post_id = await _insert_post(pg_session_maker)

        publish_fn = AsyncMock(return_value=7)

        delete_task = asyncio.create_task(delete_post(post_id, pg_session_maker))
        approve_task = asyncio.create_task(approve_post(post_id, _CHANNEL_TG_ID, publish_fn, pg_session_maker))
        results = await asyncio.gather(delete_task, approve_task, return_exceptions=True)
        assert not any(isinstance(r, Exception) for r in results)

        final = await _read_post(pg_session_maker, post_id)
        # Final status is one of the two transitions (never stuck as DRAFT).
        assert final.status in (PostStatus.APPROVED, PostStatus.SKIPPED)


class TestDailySlotReservationAtomic:
    """`try_reserve_daily_slot` uses UPDATE ... RETURNING — must stay atomic under concurrency."""

    async def test_concurrent_slot_reservations_respect_limit(self, pg_session_maker):
        """Fire N concurrent reservations against a channel with max=3 → exactly 3 succeed."""
        max_posts = 3
        concurrency = 8
        await _insert_channel(pg_session_maker, max_posts_per_day=max_posts, daily_count=0)

        tasks = [try_reserve_daily_slot(pg_session_maker, _CHANNEL_TG_ID) for _ in range(concurrency)]
        results = await asyncio.gather(*tasks)

        # Exactly `max_posts` succeed; the rest are denied.
        assert sum(results) == max_posts

        # Verify the stored counter matches.
        async with pg_session_maker() as session:
            ch = (await session.execute(select(Channel).where(Channel.telegram_id == _CHANNEL_TG_ID))).scalar_one()
            assert ch.daily_posts_count == max_posts

    async def test_no_channel_row_returns_true(self, pg_session_maker):
        """If no channel row exists, reservation is a no-op that returns True (no limit to enforce)."""
        ok = await try_reserve_daily_slot(pg_session_maker, _CHANNEL_TG_ID)
        assert ok is True

    async def test_limit_reached_returns_false(self, pg_session_maker):
        """Channel already at the daily limit rejects further reservations."""
        await _insert_channel(pg_session_maker, max_posts_per_day=2, daily_count=2)

        first = await try_reserve_daily_slot(pg_session_maker, _CHANNEL_TG_ID)
        assert first is False


class TestConcurrentSchedule:
    """schedule_post uses FOR UPDATE on ChannelPost — concurrent calls must not double-schedule."""

    async def test_concurrent_schedule_single_success(self, pg_session_maker):
        """Two schedule_post calls race on the same post — only one schedules via Telethon."""
        await _insert_channel(pg_session_maker, max_posts_per_day=5)
        post_id = await _insert_post(pg_session_maker)

        async with pg_session_maker() as session:
            channel = (await session.execute(select(Channel).where(Channel.telegram_id == _CHANNEL_TG_ID))).scalar_one()

        telethon_stub = AsyncMock()
        telethon_stub.send_scheduled_message = AsyncMock(return_value=AsyncMock(message_id=55))
        telethon_stub.send_scheduled_photo = AsyncMock(return_value=AsyncMock(message_id=55))

        publish_time = utc_now() + timedelta(hours=2)

        t1 = asyncio.create_task(schedule_post(telethon_stub, pg_session_maker, post_id, channel, publish_time))
        t2 = asyncio.create_task(schedule_post(telethon_stub, pg_session_maker, post_id, channel, publish_time))
        m1, m2 = await asyncio.gather(t1, t2)

        # Exactly one scheduled, one got "Already scheduled." (FOR UPDATE serialized).
        scheduled_count = sum(1 for msg in (m1, m2) if msg.startswith("Scheduled"))
        already_count = sum(1 for msg in (m1, m2) if msg == "Already scheduled.")
        assert scheduled_count == 1, f"expected 1 scheduled, got: {m1!r} / {m2!r}"
        assert already_count == 1, f"expected 1 already-scheduled, got: {m1!r} / {m2!r}"

        # Telethon send called exactly once thanks to the lock + status guard.
        total_sends = telethon_stub.send_scheduled_message.call_count + telethon_stub.send_scheduled_photo.call_count
        assert total_sends == 1

        final = await _read_post(pg_session_maker, post_id)
        assert final.status == PostStatus.SCHEDULED
        assert final.scheduled_telegram_id == 55
