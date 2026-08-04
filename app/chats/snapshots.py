"""Periodic member-count snapshots, over the Bot API.

Runs as one background task in the bot process. It used to read through the
Telethon client and had never written a row: that client is a per-process
singleton wired at the bot's startup, the loop was started from the web API,
and the account's session lives on a developer's machine rather than on the
server. The client API was never needed here — the moderator bot is an
administrator in every managed chat, and `getChatMemberCount` is a bot method.

Intentionally simple: two calls per chat per tick, no concurrency, no
deduplication. If the process dies we lose the in-flight tick and nothing is
corrupted, because each snapshot is an independent row.

Each tick also refreshes the title and photo of chats whose ``last_synced_at``
is older than ``METADATA_STALENESS_HOURS``. That check uses ``last_synced_at``
and not ``modified_at``, so an admin's edit in the console does not suppress a
Telegram sync and a Telegram sync does not masquerade as an admin's edit.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.chats.metadata import fetch_member_count, fetch_metadata
from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.models import Chat, ChatMemberSnapshot

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("chats.snapshots")

SNAPSHOT_INTERVAL_SECONDS = 3600  # 1 hour
METADATA_STALENESS_HOURS = 24


def _apply_title(chat: Chat, title: str | None) -> bool:
    """Take Telegram's title. True when it actually differed.

    Only the title, because it is the one upstream-managed string the console
    shows; welcome text, captcha, parent and notes are the admin's and must not
    be overwritten by a sync.
    """
    if not title or title == chat.title:
        return False
    chat.title = title
    return True


async def snapshot_once(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    bot: Bot,
) -> int:
    """Record one member count per chat. Returns how many rows were written.

    A chat Telegram will not answer about is skipped rather than written as
    zero, and the rest of the tick continues — on forty-five chats, one of them
    having removed the bot is an ordinary Tuesday.
    """
    written = 0
    refreshed = 0
    photo_refreshed = 0
    now = utc_now()
    cutoff = now - datetime.timedelta(hours=METADATA_STALENESS_HOURS)

    async with session_maker() as session:
        chats = (await session.execute(select(Chat))).scalars().all()
        for chat in chats:
            members = await fetch_member_count(bot=bot, chat_id=chat.id)
            if members is not None:
                session.add(ChatMemberSnapshot(chat_id=chat.id, member_count=members))
                written += 1

            if chat.last_synced_at is not None and chat.last_synced_at >= cutoff:
                continue

            metadata = await fetch_metadata(bot=bot, chat_id=chat.id)
            if metadata is None:
                continue
            if _apply_title(chat, metadata.title):
                refreshed += 1
            if metadata.photo_file_id and metadata.photo_file_id != chat.photo_file_id:
                chat.photo_file_id = metadata.photo_file_id
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
    bot: Bot,
    interval_seconds: int = SNAPSHOT_INTERVAL_SECONDS,
) -> None:
    """Forever-loop. Cancelled on shutdown via task.cancel().

    No waiting for anything to connect: the bot token works from the first
    call, which is most of the point of having moved off the client API.
    """
    while True:
        try:
            await snapshot_once(session_maker=session_maker, bot=bot)
        except Exception:
            logger.exception("snapshot_loop iteration failed")
        await asyncio.sleep(interval_seconds)
