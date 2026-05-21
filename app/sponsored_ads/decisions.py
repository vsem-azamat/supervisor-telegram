"""Apply a moderator's decision on a flagged ad: delete / ban, then react."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.sponsored_ads import cleanup, outreach
from app.sponsored_ads.leads import AdLeadRepository

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("sponsored_ads.decisions")

_SNIPPET_CHARS = 300
_REACHED_LABEL = {
    "dm": "написали в ЛС",
    "ping": "пинг в чате",
    "failed": "связаться не удалось",
}


async def apply_ad_decision(
    bot: Bot,
    db: AsyncSession,
    *,
    action: str,
    chat_id: int,
    message_id: int,
    user_id: int,
) -> str:
    """Execute a `delete` or `ban` decision. Returns a short HTML status line.

    `delete` → remove the ad + cross-chat duplicates, create a lead, reach the
    advertiser. `ban` → remove the ad + duplicates, ban the user, no outreach.
    """
    result = await cleanup.delete_ad_duplicates(
        bot,
        db,
        user_id=user_id,
        origin_chat_id=chat_id,
        origin_message_id=message_id,
    )

    if action == "ban":
        try:
            await bot.ban_chat_member(chat_id, user_id)
            banned = True
        except Exception as err:
            logger.warning("ad_ban_failed", error=str(err), user_id=user_id, chat_id=chat_id)
            banned = False
        suffix = "забанен" if banned else "бан не удался"
        return f"🚫 <b>Удалено сообщений: {result.deleted}. Пользователь {suffix}.</b>"

    # action == "delete"
    snippet = result.origin_text[:_SNIPPET_CHARS] if result.origin_text else None
    lead_repo = AdLeadRepository(db)
    lead = await lead_repo.create_lead(chat_id=chat_id, user_id=user_id, snippet=snippet)
    reached_via = await outreach.reach_advertiser(
        bot,
        user_id=user_id,
        origin_chat_id=chat_id,
        lead_id=lead.id,
    )
    await lead_repo.set_reached_via(lead.id, reached_via)
    label = _REACHED_LABEL[reached_via]
    return f"🗑 <b>Удалено сообщений: {result.deleted}. Рекламодатель: {label}.</b>"
