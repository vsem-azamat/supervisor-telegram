from __future__ import annotations

from decimal import Decimal

from app.sponsored_ads.domain import (
    AdCategoryPolicy,
    AdRequestStatus,
    QuoteProposal,
    SponsoredAdPricingConfig,
    calculate_quote_range,
    can_show_payment_instructions,
    validate_quote_proposal,
)


def test_calculate_quote_range_uses_chat_floor_price() -> None:
    quote = calculate_quote_range(
        SponsoredAdPricingConfig(
            chat_base_price=500,
            chat_floor_price=450,
            category_multiplier=Decimal("0.8"),
            format_multiplier=Decimal("1.0"),
            pin_multiplier=Decimal("1.0"),
            negotiation_floor_multiplier=Decimal("0.85"),
            negotiation_ceiling_multiplier=Decimal("1.20"),
            currency="CZK",
        )
    )

    assert quote.recommended_price == 400
    assert quote.minimum_price == 450
    assert quote.maximum_price == 480
    assert quote.currency == "CZK"


def test_calculate_quote_range_uses_negotiation_floor_when_above_chat_floor() -> None:
    quote = calculate_quote_range(
        SponsoredAdPricingConfig(
            chat_base_price=500,
            chat_floor_price=350,
            category_multiplier=Decimal("0.8"),
            format_multiplier=Decimal("1.3"),
            pin_multiplier=Decimal("1.0"),
            negotiation_floor_multiplier=Decimal("0.85"),
            negotiation_ceiling_multiplier=Decimal("1.20"),
            currency="CZK",
        )
    )

    assert quote.recommended_price == 520
    assert quote.minimum_price == 442
    assert quote.maximum_price == 624


def test_validate_quote_rejects_blocked_category_before_payment() -> None:
    quote = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=500, chat_floor_price=350))

    result = validate_quote_proposal(
        QuoteProposal(price=500, category_policy=AdCategoryPolicy.BLOCKED),
        quote,
    )

    assert not result.is_valid
    assert result.reason == "blocked_category"


def test_validate_quote_rejects_out_of_bounds_without_admin_override() -> None:
    quote = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=500, chat_floor_price=350))

    low = validate_quote_proposal(QuoteProposal(price=349), quote)
    high = validate_quote_proposal(QuoteProposal(price=701), quote)

    assert not low.is_valid
    assert low.reason == "below_minimum"
    assert not high.is_valid
    assert high.reason == "above_maximum"


def test_validate_quote_allows_admin_override_outside_bounds() -> None:
    quote = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=500, chat_floor_price=350))

    result = validate_quote_proposal(QuoteProposal(price=300, admin_override=True), quote)

    assert result.is_valid
    assert result.reason is None


def test_validate_quote_rejects_disabled_pinning() -> None:
    quote = calculate_quote_range(SponsoredAdPricingConfig(chat_base_price=500, chat_floor_price=350))

    result = validate_quote_proposal(
        QuoteProposal(price=500, wants_pin=True, pin_enabled=False),
        quote,
    )

    assert not result.is_valid
    assert result.reason == "pinning_disabled"


def test_payment_instructions_are_visible_only_in_awaiting_payment() -> None:
    assert can_show_payment_instructions(AdRequestStatus.AWAITING_PAYMENT)
    assert not can_show_payment_instructions(AdRequestStatus.NEGOTIATING)
    assert not can_show_payment_instructions(AdRequestStatus.PENDING_ADMIN_REVIEW)
    assert not can_show_payment_instructions(AdRequestStatus.REJECTED)
