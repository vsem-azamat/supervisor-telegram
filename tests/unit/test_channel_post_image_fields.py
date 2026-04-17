"""Regression test: image_candidates and image_phashes fields on ChannelPost."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.core.enums import PostStatus
from app.db.models import ChannelPost
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_channel_post_image_candidates_roundtrip(session_maker: async_sessionmaker):
    """image_candidates JSON field persists a list-of-dicts and reads back equal."""
    payload = [
        {"url": "https://example.com/a.jpg", "source": "og_image", "quality_score": 8, "selected": True},
        {"url": "https://example.com/b.jpg", "source": "article_body", "quality_score": 6, "selected": False},
    ]
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=-100,
            external_id="ext1",
            title="Title",
            post_text="Body",
            status=PostStatus.DRAFT,
        )
        post.image_candidates = payload
        post.image_phashes = ["a3f8d2c1b9e47f05"]
        session.add(post)
        await session.commit()
        await session.refresh(post)

        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == post.id))).scalar_one()
        assert row.image_candidates == payload
        assert row.image_phashes == ["a3f8d2c1b9e47f05"]


async def test_channel_post_image_fields_default_to_none(session_maker: async_sessionmaker):
    """Both fields are nullable and None by default — backward compatible."""
    async with session_maker() as session:
        post = ChannelPost(
            channel_id=-100,
            external_id="ext2",
            title="Title",
            post_text="Body",
            status=PostStatus.DRAFT,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        assert post.image_candidates is None
        assert post.image_phashes is None
