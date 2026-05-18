from __future__ import annotations

from decimal import Decimal

import pytest
from app.db.models import Chat, Message
from app.db.repositories.sponsored_ads import SponsoredAdRequestRepository
from app.sponsored_ads.domain import (
    AdCategoryPolicy,
    AdRequestStatus,
    QuoteProposal,
    SponsoredAdPricingConfig,
    calculate_quote_range,
)
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_create_request_from_flagged_message(session) -> None:
    chat = Chat(id=-100100, title="Admissions chat")
    flagged_message = Message(
        chat_id=chat.id,
        user_id=42,
        message_id=777,
        message="Need entrance exam tutor? DM me",
        message_info={"from": {"username": "seller"}},
        spam=True,
    )
    session.add_all([chat, flagged_message])
    await session.commit()

    repo = SponsoredAdRequestRepository(session)
    request = await repo.create_from_flagged_message(
        target_chat_id=chat.id,
        advertiser_user_id=flagged_message.user_id,
        source_message_id=flagged_message.message_id,
        source_message_text=flagged_message.message,
    )

    assert request.id is not None
    assert request.target_chat_id == chat.id
    assert request.advertiser_user_id == 42
    assert request.source_message_id == 777
    assert request.status == AdRequestStatus.DRAFT
    assert request.content_text == "Need entrance exam tutor? DM me"


async def test_accept_quote_persists_bounds_and_provenance(session) -> None:
    repo = SponsoredAdRequestRepository(session)
    request = await repo.create_from_flagged_message(
        target_chat_id=-100100,
        advertiser_user_id=42,
        source_message_id=777,
        source_message_text="Tutoring ad",
    )
    quote_range = calculate_quote_range(
        SponsoredAdPricingConfig(
            chat_base_price=1000,
            chat_floor_price=700,
            category_multiplier=Decimal("1.0"),
        )
    )

    await repo.accept_quote(
        request.id,
        proposal=QuoteProposal(price=900, category_policy=AdCategoryPolicy.ALLOWED),
        quote_range=quote_range,
        category="tutoring",
        provenance={
            "agent_summary": "Advertiser accepted a discounted tutoring placement.",
            "factors": ["base chat price", "tutoring category"],
        },
    )

    saved = await repo.get_by_id(request.id)
    assert saved is not None
    assert saved.status == AdRequestStatus.PENDING_ADMIN_REVIEW
    assert saved.category == "tutoring"
    assert saved.category_policy == AdCategoryPolicy.ALLOWED
    assert saved.quote_recommended_price == 1000
    assert saved.quote_min_price == 850
    assert saved.quote_max_price == 1200
    assert saved.final_price == 900
    assert saved.currency == "CZK"
    assert saved.quote_provenance is not None
    assert saved.quote_provenance["agent_summary"] == "Advertiser accepted a discounted tutoring placement."


async def test_accept_quote_rejects_out_of_bounds_price_without_admin_override(session) -> None:
    repo = SponsoredAdRequestRepository(session)
    request = await repo.create_from_flagged_message(
        target_chat_id=-100100,
        advertiser_user_id=42,
        source_message_id=777,
        source_message_text="Tutoring ad",
    )
    quote_range = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=1000, chat_floor_price=700))

    with pytest.raises(ValueError, match="below_minimum"):
        await repo.accept_quote(
            request.id,
            proposal=QuoteProposal(price=500, category_policy=AdCategoryPolicy.ALLOWED),
            quote_range=quote_range,
            category="tutoring",
            provenance={"agent_summary": "Too cheap"},
        )

    saved = await repo.get_by_id(request.id)
    assert saved is not None
    assert saved.status == AdRequestStatus.DRAFT
    assert saved.final_price is None


async def test_accept_quote_rejects_blocked_category_without_mutating(session) -> None:
    repo = SponsoredAdRequestRepository(session)
    request = await repo.create_from_flagged_message(
        target_chat_id=-100100,
        advertiser_user_id=42,
        source_message_id=777,
        source_message_text="Hidden earpiece ad",
    )
    quote_range = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=1000, chat_floor_price=700))

    with pytest.raises(ValueError, match="blocked_category"):
        await repo.accept_quote(
            request.id,
            proposal=QuoteProposal(price=1000, category_policy=AdCategoryPolicy.BLOCKED),
            quote_range=quote_range,
            category="exam_cheating",
            provenance={"agent_summary": "Blocked"},
        )

    saved = await repo.get_by_id(request.id)
    assert saved is not None
    assert saved.status == AdRequestStatus.DRAFT
    assert saved.category is None
    assert saved.final_price is None


async def test_accept_quote_does_not_reopen_payment_flow(session) -> None:
    repo = SponsoredAdRequestRepository(session)
    request = await repo.create_from_flagged_message(
        target_chat_id=-100100,
        advertiser_user_id=42,
        source_message_id=777,
        source_message_text="Tutoring ad",
    )
    quote_range = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=1000, chat_floor_price=700))
    await repo.accept_quote(
        request.id,
        proposal=QuoteProposal(price=1000, category_policy=AdCategoryPolicy.ALLOWED),
        quote_range=quote_range,
        category="tutoring",
        provenance={"agent_summary": "Accepted"},
    )
    await repo.approve_for_payment(request.id, admin_id=1)

    with pytest.raises(ValueError, match="quote_already_accepted"):
        await repo.accept_quote(
            request.id,
            proposal=QuoteProposal(price=900, category_policy=AdCategoryPolicy.ALLOWED),
            quote_range=quote_range,
            category="tutoring",
            provenance={"agent_summary": "Late discount"},
        )

    saved = await repo.get_by_id(request.id)
    assert saved is not None
    assert saved.status == AdRequestStatus.AWAITING_PAYMENT
    assert saved.final_price == 1000
    assert saved.approved_by_admin_id == 1


async def test_confirm_payment_only_after_admin_review(session) -> None:
    repo = SponsoredAdRequestRepository(session)
    request = await repo.create_from_flagged_message(
        target_chat_id=-100100,
        advertiser_user_id=42,
        source_message_id=777,
        source_message_text="Tutoring ad",
    )

    with pytest.raises(ValueError, match="not_awaiting_payment"):
        await repo.confirm_payment(request.id, confirmed_by_admin_id=1)

    quote_range = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=1000, chat_floor_price=700))
    await repo.accept_quote(
        request.id,
        proposal=QuoteProposal(price=1000, category_policy=AdCategoryPolicy.ALLOWED),
        quote_range=quote_range,
        category="tutoring",
        provenance={"agent_summary": "Accepted"},
    )
    with pytest.raises(ValueError, match="not_awaiting_payment"):
        await repo.confirm_payment(request.id, confirmed_by_admin_id=1)

    await repo.approve_for_payment(request.id, admin_id=1)
    await repo.confirm_payment(request.id, confirmed_by_admin_id=1)

    saved = (await session.execute(select(repo.model).where(repo.model.id == request.id))).scalar_one()
    assert saved.status == AdRequestStatus.PAYMENT_CONFIRMED
    assert saved.payment_confirmed_by_admin_id == 1
    assert saved.payment_confirmed_at is not None
