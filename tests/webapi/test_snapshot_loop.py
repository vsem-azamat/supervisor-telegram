"""Test: snapshot_once reads chats, queries telethon, writes snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.db.models import Chat, ChatMemberSnapshot
from app.webapi.snapshot_loop import snapshot_once
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
