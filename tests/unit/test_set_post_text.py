"""Service: set_post_text (verbatim text replacement)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.channel.review.service import set_post_text
from app.core.enums import PostStatus
from app.db.models import Channel, ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession, *, status: PostStatus = PostStatus.DRAFT) -> int:
    ch = Channel(name="ch", language="en", telegram_id=-100100)
    session.add(ch)
    await session.flush()
    post = ChannelPost(
        channel_id=ch.telegram_id,
        external_id="x" * 16,
        title="t",
        post_text="original",
        status=status,
    )
    session.add(post)
    await session.commit()
    return post.id


async def test_updates_text(session: AsyncSession, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
    post_id = await _seed(session)
    msg = await set_post_text(post_id, "new text", db_session_maker)
    assert "updated" in msg.lower()


async def test_rejects_empty_text(session: AsyncSession, db_session_maker: async_sessionmaker[AsyncSession]) -> None:
    post_id = await _seed(session)
    msg = await set_post_text(post_id, "  ", db_session_maker)
    assert "empty" in msg.lower()


async def test_blocks_edit_after_publish(
    session: AsyncSession, db_session_maker: async_sessionmaker[AsyncSession]
) -> None:
    post_id = await _seed(session, status=PostStatus.APPROVED)
    msg = await set_post_text(post_id, "new", db_session_maker)
    assert "Already published" in msg
