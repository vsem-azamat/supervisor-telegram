"""ORM round-trip for ChannelPost.review_album_message_ids."""

from __future__ import annotations

import pytest
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_review_album_message_ids_roundtrips_list_of_ints(session_maker):
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
            review_album_message_ids=[1001, 1002, 1003],
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        pid = p.id

    async with session_maker() as s:
        row = (await s.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
        assert row.review_album_message_ids == [1001, 1002, 1003]


async def test_review_album_message_ids_defaults_to_none(session_maker):
    async with session_maker() as s:
        p = ChannelPost(
            channel_id=-100,
            external_id="y",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        assert p.review_album_message_ids is None
