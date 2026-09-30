"""Who a business writes to about advertising.

The ads page is a showcase: it hands the conversation to a person in
Telegram. Who that person is lives in `ADS_CONTACT`, not in the frontend
bundle, and an unset or malformed value means no button rather than a link to
nowhere. See docs/architecture.md, «The ads page is a showcase, not a shop».
"""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.core.config import Settings, get_settings

from .conftest import app_for

pytestmark = pytest.mark.asyncio


async def _ads(session: AsyncSession, contact: str | None) -> dict:
    app = app_for(session)
    configured = Settings(_env_file=None, ads_contact=contact)
    app.dependency_overrides[get_settings] = lambda: configured
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get("/api/v1/ads")
    assert response.status_code == 200
    return response.json()


async def test_the_contact_is_a_telegram_link(session: AsyncSession) -> None:
    body = await _ads(session, "konnekt_ads")
    assert body == {"contact_url": "https://t.me/konnekt_ads"}


async def test_an_at_sign_is_forgiven(session: AsyncSession) -> None:
    body = await _ads(session, "@konnekt_ads")
    assert body["contact_url"] == "https://t.me/konnekt_ads"


async def test_no_contact_means_no_link(session: AsyncSession) -> None:
    assert (await _ads(session, None))["contact_url"] is None
    assert (await _ads(session, ""))["contact_url"] is None


async def test_a_value_that_is_not_a_username_refuses_to_start() -> None:
    """A typo in a deploy variable fails at boot, not as a broken link."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ads_contact="https://t.me/x")


# ── the example card on the ads page ────────────────────────────────────


async def _one_placement(session: AsyncSession) -> int:
    from students_cz.db.models.enums import PlacementSlot, UiLang
    from students_cz.db.models.partners import (
        Partner,
        PartnerOffer,
        PartnerOfferI18n,
        Placement,
    )

    partner = Partner(code="ads-test-insurer", name="Insurer")
    session.add(partner)
    await session.flush()
    offer = PartnerOffer(partner_id=partner.id, url="https://example.test/offer")
    session.add(offer)
    await session.flush()
    session.add(PartnerOfferI18n(offer_id=offer.id, lang=UiLang.RU, title="Страховка"))
    placement = Placement(offer_id=offer.id, slot=PlacementSlot.PROFILE_FOOTER)
    session.add(placement)
    await session.flush()
    return placement.id


async def _impressions(session: AsyncSession, placement_id: int) -> int:
    from sqlalchemy import func, select

    from students_cz.db.models.enums import PlacementEventKind
    from students_cz.db.models.partners import PlacementEvent

    count = await session.scalar(
        select(func.count(PlacementEvent.id)).where(
            PlacementEvent.placement_id == placement_id,
            PlacementEvent.kind == PlacementEventKind.IMPRESSION,
        )
    )
    return count or 0


async def test_a_preview_shows_the_card_and_counts_no_impression(client, session) -> None:
    """A business looking at the ads page is not a student seeing the offer.

    Counted, it would bill the partner for our own showcase.
    """
    from .conftest import auth_header

    placement_id = await _one_placement(session)
    response = await client.get(
        "/api/v1/placements",
        params={"slot": "profile_footer", "preview": "true"},
        headers=auth_header(90431),
    )
    assert response.status_code == 200
    assert placement_id in [p["id"] for p in response.json()]
    assert await _impressions(session, placement_id) == 0


async def test_an_ordinary_view_still_counts(client, session) -> None:
    from .conftest import auth_header

    placement_id = await _one_placement(session)
    response = await client.get(
        "/api/v1/placements",
        params={"slot": "profile_footer"},
        headers=auth_header(90432),
    )
    assert response.status_code == 200
    assert await _impressions(session, placement_id) == 1
