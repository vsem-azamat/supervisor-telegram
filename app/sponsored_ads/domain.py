from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class AdCategoryPolicy(StrEnum):
    """Policy states for sponsored ad categories."""

    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    BLOCKED = "blocked"


class AdRequestStatus(StrEnum):
    """Product-level sponsored ad request states."""

    DRAFT = "draft"
    NEGOTIATING = "negotiating"
    NEEDS_ADMIN_ATTENTION = "needs_admin_attention"
    PENDING_ADMIN_REVIEW = "pending_admin_review"
    REJECTED = "rejected"
    AWAITING_PAYMENT = "awaiting_payment"
    PAYMENT_CONFIRMED = "payment_confirmed"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class SponsoredAdPricingConfig:
    """Static inputs that create the guardrails for an ad quote."""

    chat_base_price: int
    chat_floor_price: int
    category_multiplier: Decimal = Decimal("1.0")
    format_multiplier: Decimal = Decimal("1.0")
    pin_multiplier: Decimal = Decimal("1.0")
    negotiation_floor_multiplier: Decimal = Decimal("0.85")
    negotiation_ceiling_multiplier: Decimal = Decimal("1.20")
    currency: str = "CZK"


@dataclass(frozen=True)
class QuoteRange:
    """Computed quote bounds visible to deterministic validators."""

    recommended_price: int
    minimum_price: int
    maximum_price: int
    currency: str


@dataclass(frozen=True)
class QuoteProposal:
    """A price proposal from the Agent Bot or admin."""

    price: int
    category_policy: AdCategoryPolicy = AdCategoryPolicy.ALLOWED
    wants_pin: bool = False
    pin_enabled: bool = False
    admin_override: bool = False


@dataclass(frozen=True)
class QuoteValidationResult:
    """Validation outcome for a quote proposal."""

    is_valid: bool
    reason: str | None = None


def _round_money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_quote_range(config: SponsoredAdPricingConfig) -> QuoteRange:
    """Calculate recommended, minimum, and maximum whole-unit prices."""

    recommended = _round_money(
        Decimal(config.chat_base_price) * config.category_multiplier * config.format_multiplier * config.pin_multiplier
    )
    negotiated_floor = _round_money(Decimal(recommended) * config.negotiation_floor_multiplier)
    minimum = max(config.chat_floor_price, negotiated_floor)
    maximum = _round_money(Decimal(recommended) * config.negotiation_ceiling_multiplier)
    return QuoteRange(
        recommended_price=recommended,
        minimum_price=minimum,
        maximum_price=maximum,
        currency=config.currency,
    )


def validate_quote_proposal(proposal: QuoteProposal, quote_range: QuoteRange) -> QuoteValidationResult:
    """Validate a proposed price against category, add-on, and price gates."""

    if proposal.category_policy is AdCategoryPolicy.BLOCKED:
        return QuoteValidationResult(is_valid=False, reason="blocked_category")
    if proposal.wants_pin and not proposal.pin_enabled:
        return QuoteValidationResult(is_valid=False, reason="pinning_disabled")
    if proposal.admin_override:
        return QuoteValidationResult(is_valid=True)
    if proposal.price < quote_range.minimum_price:
        return QuoteValidationResult(is_valid=False, reason="below_minimum")
    if proposal.price > quote_range.maximum_price:
        return QuoteValidationResult(is_valid=False, reason="above_maximum")
    return QuoteValidationResult(is_valid=True)


def can_show_payment_instructions(status: AdRequestStatus) -> bool:
    """Payment instructions are visible only after admin approval."""

    return status is AdRequestStatus.AWAITING_PAYMENT
