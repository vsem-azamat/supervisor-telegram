"""Periodic member-count snapshot collector.

Runs as a single background asyncio task for the lifetime of the webapi
process. Intentionally simple: one query per chat per tick, no concurrency,
no deduplication. If the process dies, we lose the in-flight tick; no
state is corrupted because each snapshot is an independent row.

Each tick also opportunistically refreshes Chat.title from Telegram for
rows that haven't been touched in METADATA_STALENESS_HOURS — admins who
edited a row recently keep their values, but long-untouched rows pick up
upstream renames automatically.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.telethon.telethon_client import TelethonClient

logger = get_logger("webapi.snapshot_loop")

SNAPSHOT_INTERVAL_SECONDS = 3600  # 1 hour
METADATA_STALENESS_HOURS = 24


def _refresh_stale_metadata(chat: Chat, info: Any, *, cutoff: datetime.datetime) -> bool:
    """Sync Chat.title from Telegram when the row's been untouched past the cutoff.

    Returns True iff the title actually changed — caller uses that to count
    refreshes for the log line. We only sync title because that's the only
    upstream-managed string surfaced in the UI; everything else (welcome,
    captcha, parent, notes) is admin-owned.
    """
    if chat.modified_at and chat.modified_at >= cutoff:
        return False
    upstream_title = getattr(info, "title", None)
    if not isinstance(upstream_title, str) or not upstream_title:
        return False
    if upstream_title == chat.title:
        return False
    chat.title = upstream_title
    return True


async def snapshot_once(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telethon: TelethonClient | None,
) -> int:
    """Capture one snapshot per chat. Returns the number of snapshot rows
    written. Stale-metadata refreshes happen opportunistically and are logged
    separately."""
    if telethon is None or not telethon.is_available:
        logger.info("snapshot_once skipped — telethon unavailable")
        return 0

    written = 0
    refreshed = 0
    cutoff = utc_now() - datetime.timedelta(hours=METADATA_STALENESS_HOURS)
    async with session_maker() as session:
        chats = (await session.execute(select(Chat))).scalars().all()
        for chat in chats:
            try:
                info = await telethon.get_chat_info(chat.id)
            except Exception as e:  # noqa: BLE001
                logger.warning("get_chat_info failed", chat_id=chat.id, error=str(e))
                continue
            if info is None:
                continue
            if info.member_count is not None:
                session.add(ChatMemberSnapshot(chat_id=chat.id, member_count=info.member_count))
                written += 1
            if _refresh_stale_metadata(chat, info, cutoff=cutoff):
                refreshed += 1
        await session.commit()
    logger.info("snapshot_once committed", snapshots=written, metadata_refreshed=refreshed)
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
