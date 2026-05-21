"""Cross-chat cleanup of an advertiser's duplicate ad messages."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.time import utc_now
from app.db.models import Message
from app.sponsored_ads.text import normalize_text

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("sponsored_ads.cleanup")


@dataclass(frozen=True)
class CleanupResult:
    deleted: int
    origin_text: str | None


async def delete_ad_duplicates(
    bot: Bot,
    db: AsyncSession,
    *,
    user_id: int,
    origin_chat_id: int,
    origin_message_id: int,
    window_hours: int = 24,
) -> CleanupResult:
    """Delete the origin ad and every identical message from the same user.

    "Identical" = same normalized text, posted within `window_hours`, in any
    chat. The origin pair is always attempted, even if its `messages` row is
    missing. Per-message delete failures are logged and skipped.
    """
    cutoff = utc_now() - datetime.timedelta(hours=window_hours)

    origin_row = (
        (
            await db.execute(
                select(Message).where(
                    Message.chat_id == origin_chat_id,
                    Message.message_id == origin_message_id,
                )
            )
        )
        .scalars()
        .first()
    )
    origin_text = origin_row.message if origin_row else None

    pairs: set[tuple[int, int]] = {(origin_chat_id, origin_message_id)}
    if origin_text:
        target = normalize_text(origin_text)
        rows = (
            (
                await db.execute(
                    select(Message).where(
                        Message.user_id == user_id,
                        Message.timestamp >= cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.message and normalize_text(row.message) == target:
                pairs.add((row.chat_id, row.message_id))

    deleted = 0
    for chat_id, message_id in pairs:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            deleted += 1
        except Exception as err:
            logger.warning(
                "ad_duplicate_delete_failed",
                error=str(err),
                chat_id=chat_id,
                message_id=message_id,
            )
    return CleanupResult(deleted=deleted, origin_text=origin_text)
