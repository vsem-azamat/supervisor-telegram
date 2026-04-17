"""Tests for critic DB columns on Channel and ChannelPost."""

from __future__ import annotations

import pytest
from app.core.enums import PostStatus
from app.db.models import Channel, ChannelPost
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_channel_critic_enabled_default_none(session_maker):
    async with session_maker() as session:
        ch = Channel(telegram_id=-1001, name="X")
        session.add(ch)
        await session.commit()
        await session.refresh(ch)
        assert ch.critic_enabled is None


async def test_channel_critic_enabled_roundtrip(session_maker):
    async with session_maker() as session:
        ch = Channel(telegram_id=-1002, name="X", critic_enabled=True)
        session.add(ch)
        await session.commit()
        cid = ch.id

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    assert row.critic_enabled is True


async def test_channel_critic_enabled_explicit_false(session_maker):
    async with session_maker() as session:
        ch = Channel(telegram_id=-1003, name="X", critic_enabled=False)
        session.add(ch)
        await session.commit()
        cid = ch.id

    async with session_maker() as session:
        row = (await session.execute(select(Channel).where(Channel.id == cid))).scalar_one()
    assert row.critic_enabled is False


async def test_channel_post_pre_critic_text_default_none(session_maker):
    async with session_maker() as session:
        p = ChannelPost(
            channel_id=-100,
            external_id="x",
            title="t",
            post_text="b",
            status=PostStatus.DRAFT,
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        assert p.pre_critic_text is None


async def test_channel_post_pre_critic_text_roundtrip(session_maker):
    async with session_maker() as session:
        p = ChannelPost(
            channel_id=-100,
            external_id="y",
            title="t",
            post_text="new",
            status=PostStatus.DRAFT,
            pre_critic_text="original pre-critic text with **bold**",
        )
        session.add(p)
        await session.commit()
        pid = p.id

    async with session_maker() as session:
        row = (await session.execute(select(ChannelPost).where(ChannelPost.id == pid))).scalar_one()
    assert row.pre_critic_text == "original pre-critic text with **bold**"


async def test_generated_post_pre_critic_text_default_none():
    from app.channel.generator import GeneratedPost

    p = GeneratedPost(text="hello")
    assert p.pre_critic_text is None


async def test_generated_post_pre_critic_text_roundtrip():
    from app.channel.generator import GeneratedPost

    p = GeneratedPost(text="new text", pre_critic_text="original text")
    assert p.pre_critic_text == "original text"

    dumped = p.model_dump()
    restored = GeneratedPost.model_validate(dumped)
    assert restored.pre_critic_text == "original text"
