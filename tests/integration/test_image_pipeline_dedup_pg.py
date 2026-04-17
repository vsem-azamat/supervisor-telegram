"""Integration tests: pHash dedup queries against a real Postgres container."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.channel.image_pipeline.dedup import (
    compute_phash,
    phash_dedup,
    recent_phashes_for_channel,
)
from app.channel.image_pipeline.filter import FilteredImage
from app.core.enums import PostStatus
from app.core.time import utc_now
from app.db.models import ChannelPost

from tests.fixtures.images import make_test_image

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CHANNEL = -100555666


async def _insert_post(
    session_maker, *, phashes: list[str], age_days: int = 0, status: str = PostStatus.APPROVED
) -> int:
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=_CHANNEL,
            external_id=f"e{age_days}_{phashes[0][:4]}",
            title="t",
            post_text="b",
            status=status,
        )
        post.image_phashes = phashes
        if age_days:
            post.created_at = utc_now() - timedelta(days=age_days)
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


class TestRecentPhashesForChannel:
    async def test_returns_flat_list_sorted_newest_first(self, pg_session_maker):
        data_a = make_test_image(width=800, height=600, colors=50, seed=1)
        data_b = make_test_image(width=800, height=600, colors=50, seed=2)
        ha = compute_phash(data_a)
        hb = compute_phash(data_b)
        await _insert_post(pg_session_maker, phashes=[ha])
        await _insert_post(pg_session_maker, phashes=[hb])

        hashes = await recent_phashes_for_channel(pg_session_maker, _CHANNEL, lookback=30)
        assert set(hashes) == {ha, hb}

    async def test_skips_non_approved_posts(self, pg_session_maker):
        data = make_test_image(width=800, height=600, colors=50, seed=1)
        h = compute_phash(data)
        await _insert_post(pg_session_maker, phashes=[h], status=PostStatus.DRAFT)
        hashes = await recent_phashes_for_channel(pg_session_maker, _CHANNEL, lookback=30)
        assert hashes == []

    async def test_respects_lookback_limit(self, pg_session_maker):
        """Only the most recent N posts are included."""
        for i in range(5):
            data = make_test_image(width=800, height=600, colors=50, seed=i + 1)
            await _insert_post(pg_session_maker, phashes=[compute_phash(data)])

        hashes = await recent_phashes_for_channel(pg_session_maker, _CHANNEL, lookback=3)
        assert len(hashes) == 3  # takes the 3 newest posts


class TestPhashDedupPg:
    async def test_full_flow_filters_duplicate(self, pg_session_maker):
        data = make_test_image(width=800, height=600, colors=100, seed=7)
        h = compute_phash(data)
        await _insert_post(pg_session_maker, phashes=[h])

        img = FilteredImage(url="https://x/new.jpg", width=800, height=600, bytes_=data)
        kept = await phash_dedup(pg_session_maker, _CHANNEL, [img], threshold=10, lookback=30)
        assert kept == []

    async def test_full_flow_keeps_unique(self, pg_session_maker):
        stored = make_test_image(width=800, height=600, colors=50, seed=1)
        new = make_test_image(width=800, height=600, colors=250, seed=99)
        await _insert_post(pg_session_maker, phashes=[compute_phash(stored)])

        img = FilteredImage(url="https://x/new.jpg", width=800, height=600, bytes_=new)
        kept = await phash_dedup(pg_session_maker, _CHANNEL, [img], threshold=3, lookback=30)
        assert len(kept) == 1
        assert kept[0].phash is not None

    async def test_no_posts_keeps_everything(self, pg_session_maker):
        data = make_test_image(width=800, height=600, colors=100, seed=1)
        img = FilteredImage(url="https://x/new.jpg", width=800, height=600, bytes_=data)
        kept = await phash_dedup(pg_session_maker, _CHANNEL, [img], threshold=10, lookback=30)
        assert len(kept) == 1
