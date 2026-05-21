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
    command = CommandObject(prefix="/", command="start", args=f"adlead_{lead.id}")
    await start_ad_lead(message, command, session)

    message.answer.assert_awaited_once()
    await session.refresh(lead)
    assert lead.link_clicked_at is not None
