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
    """A chat last synced >24h ago (or never) picks up its current Telegram title."""
    old = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
    async with db_session_maker() as session:
        stale = Chat(id=-300, title="Old Name")
        stale.last_synced_at = old
        session.add(stale)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=10, title="Renamed Upstream"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -300))).scalar_one()
    assert chat.title == "Renamed Upstream"
    # Sync timestamp must now be recent, so the next tick won't re-refresh.
    assert chat.last_synced_at is not None
    assert chat.last_synced_at > utc_now() - datetime.timedelta(minutes=1)


async def test_snapshot_once_skips_recently_synced_chat(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Title sync was performed <24h ago — Telethon is queried for member
    counts but title is NOT overwritten."""
    fresh = utc_now() - datetime.timedelta(hours=1)
    async with db_session_maker() as session:
        chat = Chat(id=-400, title="Cached Title")
        chat.last_synced_at = fresh
        session.add(chat)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=5, title="Telegram Default"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -400))).scalar_one()
    assert chat.title == "Cached Title"


async def test_snapshot_once_admin_edit_does_not_block_title_sync(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Admin edited the row from the web UI 5 minutes ago. last_synced_at
    is stale, so Telethon's title should still win — admin edits no longer
    suppress upstream syncs (unlike the previous modified_at-based check)."""
    stale_sync = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
    fresh_admin_edit = utc_now() - datetime.timedelta(minutes=5)
    async with db_session_maker() as session:
        chat = Chat(id=-450, title="Old DB Title")
        chat.last_synced_at = stale_sync
        chat.modified_at = fresh_admin_edit
        session.add(chat)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=12, title="Live Telegram"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -450))).scalar_one()
    assert chat.title == "Live Telegram"


async def test_snapshot_once_first_sync_for_brand_new_chat(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A chat with last_synced_at=NULL must be treated as stale (never synced)
    and pick up the upstream title on the first tick."""
    async with db_session_maker() as session:
        chat = Chat(id=-460, title="Placeholder")
        # last_synced_at left as NULL (default) — simulates a chat that's
        # been added to the DB by some pathway other than the snapshot loop.
        session.add(chat)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=3, title="Real Name"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -460))).scalar_one()
    assert chat.title == "Real Name"
    assert chat.last_synced_at is not None


async def test_snapshot_once_skips_unchanged_title(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Same title in DB and Telegram — title field is not re-assigned
    (no UPDATE for that column), but last_synced_at is still bumped because
    we successfully pulled fresh data from Telegram."""
    old = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS + 1)
    async with db_session_maker() as session:
        chat = Chat(id=-500, title="Same Name")
        chat.last_synced_at = old
        session.add(chat)
        await session.commit()

    tc = MagicMock()
    tc.is_available = True
    tc.get_chat_info = AsyncMock(return_value=MagicMock(member_count=7, title="Same Name"))

    await snapshot_once(session_maker=db_session_maker, telethon=tc)

    async with db_session_maker() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == -500))).scalar_one()
    assert chat.title == "Same Name"
    # last_synced_at must be bumped — successful query counts as a sync
    # even if title didn't change.
    assert chat.last_synced_at is not None
    assert chat.last_synced_at > utc_now() - datetime.timedelta(minutes=1)
