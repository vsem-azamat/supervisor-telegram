from unittest.mock import AsyncMock

import pytest
from aiogram.filters import CommandObject
from app.core.config import settings
from app.db.models import AdLead
from app.presentation.telegram.handlers.start import ads_command, start_ad_lead, start_ads_info
from sqlalchemy.ext.asyncio import AsyncSession


async def test_ads_command_sends_rate_card(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", "https://telegra.ph/ads")
    message = AsyncMock()
    await ads_command(message)
    message.answer.assert_awaited_once()
    assert "https://telegra.ph/ads" in message.answer.await_args.args[0]


async def test_start_ads_info_sends_rate_card() -> None:
    message = AsyncMock()
    await start_ads_info(message)
    message.answer.assert_awaited_once()


async def test_start_ad_lead_marks_click_and_sends_rate_card(session: AsyncSession) -> None:
    lead = AdLead(chat_id=-1001, user_id=777, snippet="ad")
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session, bot)

    message.answer.assert_awaited_once()
    bot.delete_message.assert_not_awaited()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None


async def test_start_ad_lead_deletes_public_ping(session: AsyncSession) -> None:
    lead = AdLead(
        chat_id=-1001,
        user_id=777,
        snippet="ad",
        reached_via="ping",
        ping_chat_id=-1001,
        ping_message_id=55,
    )
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session, bot)

    bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=55)
    message.answer.assert_awaited_once()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None
    assert lead.ping_chat_id is None
    assert lead.ping_message_id is None


async def test_start_ad_lead_still_answers_when_ping_delete_fails(session: AsyncSession) -> None:
    lead = AdLead(
        chat_id=-1001,
        user_id=777,
        snippet="ad",
        reached_via="ping",
        ping_chat_id=-1001,
        ping_message_id=55,
    )
    session.add(lead)
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    bot.delete_message.side_effect = RuntimeError("message already deleted")
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session, bot)

    bot.delete_message.assert_awaited_once_with(chat_id=-1001, message_id=55)
    message.answer.assert_awaited_once()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None
    assert lead.ping_chat_id == -1001
    assert lead.ping_message_id == 55
