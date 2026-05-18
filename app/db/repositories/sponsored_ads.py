from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.time import utc_now
from app.db.models import SponsoredAdRequest
from app.sponsored_ads.domain import (
    AdRequestStatus,
    QuoteProposal,
    QuoteRange,
    validate_quote_proposal,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SponsoredAdRequestRepository:
    model = SponsoredAdRequest

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, request_id: int) -> SponsoredAdRequest | None:
        result = await self.db.execute(select(SponsoredAdRequest).where(SponsoredAdRequest.id == request_id))
        return result.scalars().first()

    async def create_from_flagged_message(
        self,
        *,
        target_chat_id: int,
        advertiser_user_id: int,
        source_message_id: int | None,
        source_message_text: str | None,
    ) -> SponsoredAdRequest:
        request = SponsoredAdRequest(
            target_chat_id=target_chat_id,
            advertiser_user_id=advertiser_user_id,
            source_message_id=source_message_id,
            source_message_text=source_message_text,
            content_text=source_message_text,
        )
        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)
        return request

    async def accept_quote(
        self,
        request_id: int,
        *,
        proposal: QuoteProposal,
        quote_range: QuoteRange,
        category: str,
        provenance: dict[str, Any],
    ) -> SponsoredAdRequest:
        validation = validate_quote_proposal(proposal, quote_range)
        if not validation.is_valid:
            raise ValueError(validation.reason or "invalid_quote")

        request = await self._get_required(request_id)
        if request.status not in {
            AdRequestStatus.DRAFT.value,
            AdRequestStatus.NEGOTIATING.value,
            AdRequestStatus.NEEDS_ADMIN_ATTENTION.value,
        }:
            raise ValueError("quote_already_accepted")

        request.status = AdRequestStatus.PENDING_ADMIN_REVIEW
        request.category = category
        request.category_policy = proposal.category_policy
        request.wants_pin = proposal.wants_pin
        request.pin_enabled = proposal.pin_enabled
        request.quote_recommended_price = quote_range.recommended_price
        request.quote_min_price = quote_range.minimum_price
        request.quote_max_price = quote_range.maximum_price
        request.final_price = proposal.price
        request.currency = quote_range.currency
        request.admin_override = proposal.admin_override
        request.quote_provenance = provenance
        request.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(request)
        return request

    async def approve_for_payment(self, request_id: int, *, admin_id: int) -> SponsoredAdRequest:
        request = await self._get_required(request_id)
        if request.status != AdRequestStatus.PENDING_ADMIN_REVIEW:
            raise ValueError("not_pending_admin_review")

        request.status = AdRequestStatus.AWAITING_PAYMENT
        request.approved_by_admin_id = admin_id
        request.approved_at = utc_now()
        request.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(request)
        return request

    async def confirm_payment(self, request_id: int, *, confirmed_by_admin_id: int) -> SponsoredAdRequest:
        request = await self._get_required(request_id)
        if request.status != AdRequestStatus.AWAITING_PAYMENT:
            raise ValueError("not_awaiting_payment")

        request.status = AdRequestStatus.PAYMENT_CONFIRMED
        request.payment_confirmed_by_admin_id = confirmed_by_admin_id
        request.payment_confirmed_at = utc_now()
        request.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(request)
        return request

    async def _get_required(self, request_id: int) -> SponsoredAdRequest:
        request = await self.get_by_id(request_id)
        if request is None:
            raise ValueError("request_not_found")
        return request


def get_sponsored_ad_request_repository(db: AsyncSession) -> SponsoredAdRequestRepository:
    return SponsoredAdRequestRepository(db)
