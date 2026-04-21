"""ORM-level coverage for AdminSession."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.db.models import AdminSession
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_create_and_read(session: AsyncSession) -> None:
    now = datetime.datetime(2026, 4, 22, 0, 0, 0)
    s = AdminSession(
        session_id="abc" * 10,
        user_id=1,
        created_at=now,
        last_seen_at=now,
        expires_at=now + datetime.timedelta(days=30),
    )
    session.add(s)
    await session.commit()

    row = (await session.execute(select(AdminSession).where(AdminSession.session_id == s.session_id))).scalar_one()
    assert row.user_id == 1
    assert row.user_agent is None


async def test_expired_flag(session: AsyncSession) -> None:
    past = datetime.datetime(2026, 1, 1, 0, 0, 0)
    s = AdminSession(
        session_id="expired",
        user_id=1,
        created_at=past,
        last_seen_at=past,
        expires_at=past + datetime.timedelta(days=30),
    )
    session.add(s)
    await session.commit()

    assert s.expires_at < datetime.datetime(2026, 4, 22)
