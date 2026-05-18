from __future__ import annotations

import pytest
from app.db.models import Chat
from app.sponsored_ads.service import SponsoredAdRequestService

pytestmark = pytest.mark.asyncio


async def test_open_request_rejects_unknown_chat(session) -> None:
    service = SponsoredAdRequestService(session)

    with pytest.raises(ValueError, match="chat_not_found"):
        await service.open_from_flagged_message(
            target_chat_id=-100100,
            advertiser_user_id=42,
            source_message_id=777,
            source_message_text="Tutoring ad",
        )


async def test_open_request_rejects_chat_with_ads_disabled(session) -> None:
    session.add(Chat(id=-100100, title="Admissions chat", ad_enabled=False))
    await session.commit()
    service = SponsoredAdRequestService(session)

    with pytest.raises(ValueError, match="ads_disabled_for_chat"):
        await service.open_from_flagged_message(
            target_chat_id=-100100,
            advertiser_user_id=42,
            source_message_id=777,
            source_message_text="Tutoring ad",
        )


async def test_open_request_creates_for_ad_enabled_chat(session) -> None:
    session.add(Chat(id=-100100, title="Admissions chat", ad_enabled=True))
    await session.commit()
    service = SponsoredAdRequestService(session)

    request = await service.open_from_flagged_message(
        target_chat_id=-100100,
        advertiser_user_id=42,
        source_message_id=777,
        source_message_text="Tutoring ad",
    )

    assert request.target_chat_id == -100100
    assert request.advertiser_user_id == 42
    assert request.source_message_id == 777
    assert request.content_text == "Tutoring ad"
