"""Unit test: ChatMemberSnapshot ORM round-trip."""

from __future__ import annotations

import datetime

import pytest
from app.db.models import ChatMemberSnapshot
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_chat_member_snapshot_persists_and_queries(session) -> None:
    captured = datetime.datetime(2026, 4, 21, 12, 0, 0)
    snap = ChatMemberSnapshot(
        chat_id=-1001234567890,
        member_count=500,
        captured_at=captured,
    )
    session.add(snap)
    await session.commit()

    rows = (
        (await session.execute(select(ChatMemberSnapshot).where(ChatMemberSnapshot.chat_id == -1001234567890)))
        .scalars()
        .all()
    )

    assert len(rows) == 1
    assert rows[0].member_count == 500
    assert rows[0].captured_at == captured
