"""Choosing which partner block to show, and counting what happened to it.

A placement is a rule — *this offer, in this slot, when this holds* — and the
condition is JSONB so a new targeting idea is a row rather than a migration.
Matching happens here rather than in SQL because the conditions are small, few,
and easier to reason about as Python than as a JSONB containment expression
that has to express "August or September".
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from students_cz.db.models import PartnerOffer, Placement, PlacementEvent
from students_cz.db.models.enums import PlacementEventKind, UiLang
from students_cz.schemas import PlacementOut


def matches(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
    """An empty condition means "always, in this slot".

    A list is membership, a scalar is equality. A key the context does not
    know about fails closed: showing an insurance advert on the wrong screen
    is worse than showing nothing.
    """
    for key, expected in conditions.items():
        actual = context.get(key)
        if actual is None:
            return False
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


async def for_slot(
    session: AsyncSession,
    *,
    lang: UiLang,
    slot: str,
    context: dict[str, Any],
    limit: int = 3,
    count: bool = True,
) -> list[PlacementOut]:
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(Placement)
            .where(Placement.slot == slot, Placement.is_active.is_(True))
            # Newest first among equals, so the order is the same every time.
            .order_by(Placement.priority.desc(), Placement.id.desc())
            .options(
                selectinload(Placement.offer).selectinload(PartnerOffer.texts),
            )
        )
    ).all()

    out: list[PlacementOut] = []
    seen_offers: set[int] = set()
    for placement in rows:
        offer = placement.offer
        if offer is None or not offer.is_active:
            continue
        if offer.valid_from and offer.valid_from > now:
            continue
        if offer.valid_to and offer.valid_to < now:
            continue
        if offer.id in seen_offers:
            continue
        if not matches(placement.conditions, context):
            continue

        text = offer_text(offer, lang)
        if text is None:
            # An offer with no copy in any language is a data error, not
            # something to render as an empty card.
            continue

        seen_offers.add(offer.id)
        out.append(
            PlacementOut(
                id=placement.id,
                title=text.title,
                subtitle=text.subtitle,
                price_text=text.price_text,
                context_note=text.context_note,
                logo_text=offer.logo_text,
                logo_bg=offer.logo_bg,
                url=offer.url,
            )
        )
        if len(out) >= limit:
            break

    # A preview (the ads page showing a business what a card looks like) is
    # not a student seeing an offer, and counting it would bill the partner.
    if count:
        for placement_out in out:
            session.add(
                PlacementEvent(
                    placement_id=placement_out.id,
                    user_id=context.get("user_id"),
                    kind=PlacementEventKind.IMPRESSION,
                )
            )
    return out


def offer_text(offer: PartnerOffer, lang: UiLang):
    """The offer's text in the reader's language, else the first it has."""
    for text in offer.texts:
        if text.lang == lang:
            return text
    return offer.texts[0] if offer.texts else None


async def record(
    session: AsyncSession, placement_id: int, user_id: int | None, *, kind: str
) -> None:
    session.add(
        PlacementEvent(
            placement_id=placement_id,
            user_id=user_id,
            kind=PlacementEventKind(kind),
        )
    )
