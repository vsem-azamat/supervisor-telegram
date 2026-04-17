"""handle_regen rebuilds the review message when images changed."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.channel.review.telegram_io import handle_regen
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _make_post(session_maker) -> int:
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="Body",
            status=PostStatus.DRAFT,
            image_urls=["https://x/a.jpg"],
            review_message_id=1000,
            review_album_message_ids=None,
            source_items=[{"title": "t", "url": "https://src", "source_url": "https://src", "external_id": "x"}],
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_handle_regen_always_calls_rebuild(session_maker):
    pid = await _make_post(session_maker)

    # Stub out regen_post_text to return an "updated" post (same DB row, but with more images).
    async def fake_regen_post_text(post_id, api_key, model, language, session_maker, *, footer):
        async with session_maker() as s:
            r = await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = r.scalar_one_or_none()
            if post:
                post.image_urls = ["https://x/a.jpg", "https://x/new.jpg"]
                await s.commit()
                await s.refresh(post)
            return "Post regenerated.", post

    with (
        patch("app.channel.review.telegram_io.regen_post_text", side_effect=fake_regen_post_text),
        patch("app.channel.review.telegram_io._rebuild_review_message", new=AsyncMock()) as rebuild,
    ):
        bot = SimpleNamespace()
        status = await handle_regen(
            bot,
            post_id=pid,
            api_key="k",
            model="m",
            language="Russian",
            review_chat_id=-100,
            session_maker=session_maker,
            footer="— Konnekt",
        )
        assert "regenerated" in status.lower()
        rebuild.assert_awaited_once()
