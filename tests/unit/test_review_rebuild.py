"""Unit tests for _rebuild_review_message: new-first-then-delete semantics."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.channel.review.telegram_io import _rebuild_review_message
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


def _kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ok", callback_data="x")]])


async def _make_post(
    session_maker,
    *,
    review_message_id: int | None,
    album_ids: list[int] | None,
    image_urls: list[str] | None,
) -> int:
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="Body",
            status=PostStatus.DRAFT,
            review_message_id=review_message_id,
            review_album_message_ids=album_ids,
            image_urls=image_urls,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_rebuild_album_to_album_commits_new_then_deletes_old(session_maker):
    """Happy path: post has 2 images, rebuild sends new album+pult, commits, then deletes old."""
    pid = await _make_post(
        session_maker,
        review_message_id=100,
        album_ids=[200, 201],
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )

    call_order: list[str] = []
    deleted_ids_capture: list[int] = []

    bot = SimpleNamespace()

    async def fake_send_media_group(**kwargs):
        call_order.append("send_media_group")
        return [SimpleNamespace(message_id=300), SimpleNamespace(message_id=301)]

    async def fake_send_message(**kwargs):
        call_order.append("send_message")
        return SimpleNamespace(message_id=302)

    async def fake_delete_messages(**kwargs):
        call_order.append("delete_messages")
        deleted_ids_capture.extend(kwargs["message_ids"])

    bot.send_media_group = fake_send_media_group
    bot.send_message = fake_send_message
    bot.send_photo = AsyncMock()
    bot.delete_messages = fake_delete_messages

    await _rebuild_review_message(bot, -100, pid, session_maker, _kb())

    # New messages went out before the old ones were deleted.
    assert call_order == ["send_media_group", "send_message", "delete_messages"]
    # Original pult + album — order may vary, compare as a set.
    assert set(deleted_ids_capture) == {100, 200, 201}

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_message_id == 302
        assert row.review_album_message_ids == [300, 301]


async def test_rebuild_single_to_album_deletes_old_single(session_maker):
    """Post had 1 image, reviewer added another → rebuild flips to album, deletes old single."""
    pid = await _make_post(
        session_maker,
        review_message_id=500,
        album_ids=None,
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )

    deleted_ids: list[int] = []
    bot = SimpleNamespace()
    bot.send_media_group = AsyncMock(return_value=[SimpleNamespace(message_id=600), SimpleNamespace(message_id=601)])
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=602))
    bot.send_photo = AsyncMock()

    async def fake_delete_messages(**kwargs):
        deleted_ids.extend(kwargs["message_ids"])

    bot.delete_messages = fake_delete_messages

    await _rebuild_review_message(bot, -100, pid, session_maker, _kb())

    assert deleted_ids == [500]  # only the old single pult

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_message_id == 602
        assert row.review_album_message_ids == [600, 601]


async def test_rebuild_swallows_delete_errors(session_maker):
    """If delete_messages raises, DB was already committed — rebuild must not bubble the error."""
    pid = await _make_post(
        session_maker,
        review_message_id=700,
        album_ids=[701, 702],
        image_urls=["https://x/a.jpg", "https://x/b.jpg"],
    )

    bot = SimpleNamespace()
    bot.send_media_group = AsyncMock(return_value=[SimpleNamespace(message_id=800), SimpleNamespace(message_id=801)])
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=802))
    bot.send_photo = AsyncMock()

    async def failing_delete(**kwargs):
        raise RuntimeError("too old")

    bot.delete_messages = failing_delete

    # Must not raise
    await _rebuild_review_message(bot, -100, pid, session_maker, _kb())

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_message_id == 802
        assert row.review_album_message_ids == [800, 801]
