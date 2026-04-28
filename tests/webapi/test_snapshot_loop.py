"""Test: snapshot_once reads chats, queries telethon, writes snapshots."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot
from app.webapi.snapshot_loop import METADATA_STALENESS_HOURS, snapshot_once
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def test_snapshot_once_noop_without_telethon(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_maker() as session:
        session.add(Chat(id=-1, title="X"))
        await session.commit()

    await snapshot_once(session_maker=db_session_maker, telethon=None)

    async with db_session_maker() as session:
        rows = (await session.execute(select(ChatMemberSnapshot))).scalars().all()
    assert rows == []


async def test_snapshot_once_writes_rows_for_each_chat(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_maker() as session:
        session.add(Chat(id=-100, title="A"))
        session.add(Chat(id=-200, title="B"))
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(
        side_effect=[
            MagicMock(member_count=50),
            MagicMock(member_count=80),
        ]
    )

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        rows = (await session.execute(select(ChatMemberSnapshot).order_by(ChatMemberSnapshot.chat_id))).scalars().all()
    assert [(r.chat_id, r.member_count) for r in rows] == [(-200, 80), (-100, 50)]


async def test_snapshot_once_refreshes_stale_chat_title(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A chat untouched for >24h picks up its current Telegram title."""
    old = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
    async with db_session_maker() as session:
        stale = Chat(id=-300, title="Old Name")
        stale.modified_at = old
        session.add(stale)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=10, title="Renamed Upstream"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -300))).scalar_one()
    assert chat.title == "Renamed Upstream"


async def test_snapshot_once_does_not_overwrite_recent_chat(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Admin edited the row within the staleness window — Telethon's title
    should NOT win, because we treat recent admin activity as authoritative."""
    fresh = utc_now() - datetime.timedelta(hours=1)
    async with db_session_maker() as session:
        chat = Chat(id=-400, title="Admin's Choice")
        chat.modified_at = fresh
        session.add(chat)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=5, title="Telegram Default"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -400))).scalar_one()
    assert chat.title == "Admin's Choice"


async def test_snapshot_once_skips_unchanged_title(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Same title in DB and Telegram — no UPDATE fires, modified_at stays put."""
    old = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
    async with db_session_maker() as session:
        chat = Chat(id=-500, title="Same Name")
        chat.modified_at = old
        session.add(chat)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=7, title="Same Name"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -500))).scalar_one()
    # modified_at must remain the original value because no actual UPDATE
    # happened — the row didn't get bumped just from being inspected.
    assert chat.modified_at < utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS)
