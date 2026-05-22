"""Reach a would-be advertiser after their ad is removed: DM, else public ping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.sponsored_ads.rate_card import render_outreach_message, render_ping_message

if TYPE_CHECKING:
    from aiogram import Bot

logger = get_logger("sponsored_ads.outreach")


@dataclass(frozen=True)
class OutreachResult:
    reached_via: str
    ping_chat_id: int | None = None
    ping_message_id: int | None = None


async def build_smart_link(bot: Bot, lead_id: int) -> str:
    """Deep link that opens the bot on the rate card and marks the lead clicked."""
    me = await bot.me()
    return f"https://t.me/{me.username}?start=adlead_{lead_id}"


async def reach_advertiser(
    bot: Bot,
    *,
    user_id: int,
    origin_chat_id: int,
    lead_id: int,
) -> OutreachResult:
    """Try a DM first; on any failure fall back to a public ping.

    Returns the channel actually used, plus the public ping message reference
    when a ping is sent. The DM attempt is caught broadly on purpose — a bot
    cannot DM a user who never started it, and any such failure should fall
    back to the public ping.
    """
    smart_link = await build_smart_link(bot, lead_id)

    try:
        await bot.send_message(
            user_id,
            render_outreach_message(smart_link),
            disable_web_page_preview=True,
        )
        return OutreachResult("dm")
    except Exception as err:
        logger.info("ad_outreach_dm_unavailable", user_id=user_id, error=str(err))

    try:
        ping = await bot.send_message(
            origin_chat_id,
            render_ping_message(user_id, smart_link),
            disable_web_page_preview=True,
        )
        return OutreachResult("ping", ping_chat_id=origin_chat_id, ping_message_id=ping.message_id)
    except Exception as err:
        logger.warning("ad_outreach_ping_failed", chat_id=origin_chat_id, error=str(err))
        return OutreachResult("failed")
