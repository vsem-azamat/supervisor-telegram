"""handle_delete deletes pult AND album photos when present."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.channel.review.telegram_io import handle_delete
from app.core.enums import PostStatus
from app.db.models import ChannelPost

pytestmark = pytest.mark.asyncio


async def _make_post(session_maker, *, review_mid: int, album_ids: list[int] | None) -> int:
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
            review_message_id=review_mid,
            review_album_message_ids=album_ids,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p.id


async def test_delete_removes_album_plus_pult(session_maker):
    pid = await _make_post(session_maker, review_mid=100, album_ids=[101, 102, 103])
    deleted: list[int] = []

    bot = SimpleNamespace()

    async def fake_delete_messages(**kwargs):
        deleted.extend(kwargs["message_ids"])

    async def fake_delete_message(**kwargs):
        deleted.append(kwargs["message_id"])

    bot.delete_messages = fake_delete_messages
    bot.delete_message = fake_delete_message

    await handle_delete(bot, pid, -100, 100, session_maker)
    assert set(deleted) == {100, 101, 102, 103}


async def test_delete_with_no_album_still_deletes_pult(session_maker):
    pid = await _make_post(session_maker, review_mid=200, album_ids=None)
    deleted: list[int] = []

    bot = SimpleNamespace()

    async def fake_delete_message(**kwargs):
        deleted.append(kwargs["message_id"])

    async def fake_delete_messages(**kwargs):
        deleted.extend(kwargs["message_ids"])

    bot.delete_message = fake_delete_message
    bot.delete_messages = fake_delete_messages

    await handle_delete(bot, pid, -100, 200, session_maker)
    assert deleted == [200]
