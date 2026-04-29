"""Periodic member-count snapshot collector.

Runs as a single background asyncio task for the lifetime of the webapi
process. Intentionally simple: one query per chat per tick, no concurrency,
no deduplication. If the process dies, we lose the in-flight tick; no
state is corrupted because each snapshot is an independent row.

Each tick also opportunistically refreshes Chat.title from Telegram for
rows whose ``last_synced_at`` is older than ``METADATA_STALENESS_HOURS``.
The staleness check uses ``last_synced_at`` (not ``modified_at``) so that
admin edits in the web UI don't suppress Telegram syncs, and Telegram
syncs don't masquerade as admin edits.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot
from app.webapi.services.chat_sync import fetch_chat_photo_file_id

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.telethon.telethon_client import TelethonClient

logger = get_logger("webapi.snapshot_loop")

SNAPSHOT_INTERVAL_SECONDS = 3600  # 1 hour
METADATA_STALENESS_HOURS = 24


def _refresh_stale_metadata(chat: Chat, info: Any, *, cutoff: datetime.datetime) -> bool:
    """Sync Chat.title from Telegram when the row's last_synced_at is past
    the cutoff (or never set).

    Returns True iff the title actually changed — caller uses that to count
    refreshes for the log line. We only sync title because that's the only
    upstream-managed string surfaced in the UI; everything else (welcome,
    captcha, parent, notes) is admin-owned.

    The caller bumps ``last_synced_at`` separately on every successful
    Telegram pull, regardless of whether title actually changed.
    """
    if chat.last_synced_at and chat.last_synced_at >= cutoff:
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
    bot: Bot | None = None,
) -> int:
    """Capture one snapshot per chat. Returns the number of snapshot rows
    written. Stale-metadata refreshes happen opportunistically and are logged
    separately.

    If ``bot`` is provided and the chat is past the staleness cutoff, also
    fetches the chat photo's file_id via Bot API. Photo fetch failures are
    logged but do not fail the tick.
    """
    if telethon is None or not telethon.is_available:
        logger.info("snapshot_once skipped — telethon unavailable")
        return 0

    written = 0
    refreshed = 0
    photo_refreshed = 0
    now = utc_now()
    cutoff = now - datetime.timedelta(hours=METADATA_STALENESS_HOURS)
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
            sync_due = chat.last_synced_at is None or chat.last_synced_at < cutoff
            if _refresh_stale_metadata(chat, info, cutoff=cutoff):
                refreshed += 1
            if sync_due and bot is not None:
                file_id = await fetch_chat_photo_file_id(bot=bot, chat_id=chat.id)
                if file_id and file_id != chat.photo_file_id:
                    chat.photo_file_id = file_id
                    photo_refreshed += 1
            chat.last_synced_at = now
        await session.commit()
    logger.info(
        "snapshot_once committed",
        snapshots=written,
        metadata_refreshed=refreshed,
        photo_refreshed=photo_refreshed,
    )
    return written


async def run_snapshot_loop(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    telethon: TelethonClient | None,
    bot: Bot | None = None,
    interval_seconds: int = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Forever-loop. Cancelled on app shutdown via task.cancel()."""
    while True:
        try:
            await snapshot_once(session_maker=session_maker, telethon=telethon, bot=bot)
        except Exception:
            logger.exception("snapshot_loop iteration failed")
        await asyncio.sleep(interval_seconds)
