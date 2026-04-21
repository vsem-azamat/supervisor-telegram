"""Periodic member-count snapshot collector.

Runs as a single background asyncio task for the lifetime of the webapi
process. Intentionally simple: one query per chat per tick, no concurrency,
no deduplication. If the process dies, we lose the in-flight tick; no
state is corrupted because each snapshot is an independent row.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models import Chat, ChatMemberSnapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.telethon.telethon_client import TelethonClient

logger = get_logger("webapi.snapshot_loop")

SNAPSHOT_INTERVAL_SECONDS = 3600  # 1 hour


async def snapshot_once(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telethon: TelethonClient | None,
) -> int:
    """Capture one snapshot per chat. Returns the number of rows written."""
    if telethon is None or not telethon.is_available:
        logger.info("snapshot_once skipped — telethon unavailable")
        return 0

    written = 0
    async with session_maker() as session:
        chats = (await session.execute(select(Chat))).scalars().all()
        for chat in chats:
            try:
                info = await telethon.get_chat_info(chat.id)
            except Exception as e:  # noqa: BLE001
                logger.warning("get_chat_info failed", chat_id=chat.id, error=str(e))
                continue
            if info is None or info.member_count is None:
                continue
            session.add(ChatMemberSnapshot(chat_id=chat.id, member_count=info.member_count))
            written += 1
        await session.commit()
    logger.info("snapshot_once committed", rows=written)
    return written


async def run_snapshot_loop(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telethon: TelethonClient | None,
    interval_seconds: int = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Forever-loop. Cancelled on app shutdown via task.cancel()."""
    while True:
        try:
            await snapshot_once(session_maker=session_maker, telethon=telethon)
        except Exception:
            logger.exception("snapshot_loop iteration failed")
        await asyncio.sleep(interval_seconds)
