"""send_for_review persists review_album_message_ids for 2+ image posts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.channel.generator import GeneratedPost
from app.channel.review.telegram_io import send_for_review
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


class _Item:
    def __init__(self, title: str, url: str) -> None:
        self.title = title
        self.url = url
        self.body = "b"
        self.source_url = url
        self.external_id = url
        self.summary = "s"


async def _bot_with_album(album_ids: list[int], pult_id: int):
    bot = SimpleNamespace()
    bot.send_media_group = AsyncMock(return_value=[SimpleNamespace(message_id=mid) for mid in album_ids])
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=pult_id))
    bot.send_photo = AsyncMock()
    return bot


async def test_album_message_ids_persisted_when_two_images(session_maker):
    bot = await _bot_with_album(album_ids=[5001, 5002], pult_id=5003)
    post = GeneratedPost(
        text="Body\n\n——\n🔗 **Konnekt**",
        image_url="https://x/a.jpg",
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )
    items = [_Item("News", "https://src/1")]

    post_id = await send_for_review(
        bot,
        review_chat_id=-100,
        channel_id=-100,
        post=post,
        source_items=items,
        session_maker=session_maker,
    )
    assert post_id is not None

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert row.review_message_id == 5003
        assert row.review_album_message_ids == [5001, 5002]


async def test_album_message_ids_is_none_when_single_image(session_maker):
    bot = SimpleNamespace()
    bot.send_photo = AsyncMock(return_value=SimpleNamespace(message_id=6001))
    bot.send_message = AsyncMock()
    bot.send_media_group = AsyncMock()
    post = GeneratedPost(
        text="Body\n\n——\n🔗 **Konnekt**",
        image_url="https://x/a.jpg",
        image_urls=["https://x/a.jpg"],
    )
    items = [_Item("News", "https://src/1")]

    post_id = await send_for_review(
        bot,
        review_chat_id=-100,
        channel_id=-100,
        post=post,
        source_items=items,
        session_maker=session_maker,
    )

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == post_id))).scalar_one()
        assert row.review_message_id == 6001
        assert row.review_album_message_ids is None
