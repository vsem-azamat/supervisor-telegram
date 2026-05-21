import pytest
from app.core.config import settings
from app.sponsored_ads.rate_card import (
    render_outreach_message,
    render_ping_message,
    render_rate_card,
)


def test_render_rate_card_includes_article_and_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", "https://telegra.ph/ads")
    monkeypatch.setattr(settings.sponsored_ads, "sales_contact", "@konnekt_ads")
    text = render_rate_card()
    assert "https://telegra.ph/ads" in text
    assert "@konnekt_ads" in text


def test_render_rate_card_omits_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", "")
    monkeypatch.setattr(settings.sponsored_ads, "sales_contact", "")
    text = render_rate_card()
    assert "Реклама" in text  # still renders a headline, no crash


def test_render_outreach_message_embeds_link() -> None:
    text = render_outreach_message("https://t.me/bot?start=adlead_5")
    assert "https://t.me/bot?start=adlead_5" in text


def test_render_ping_message_mentions_user_and_link() -> None:
    text = render_ping_message(777, "https://t.me/bot?start=adlead_5")
    assert "tg://user?id=777" in text
    assert "https://t.me/bot?start=adlead_5" in text


def test_render_rate_card_escapes_special_characters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.sponsored_ads, "pricing_article_url", 'https://x.test/?q="><b')
    monkeypatch.setattr(settings.sponsored_ads, "sales_contact", "@a&b")
    text = render_rate_card()
    assert '"><b' not in text  # the raw quote+angle did not survive into the href
    assert "&amp;" in text  # the & in the contact was escaped


def test_render_outreach_message_escapes_link_quote() -> None:
    text = render_outreach_message('https://t.me/bot?start="evil')
    assert '"evil' not in text  # the raw double-quote did not survive into the href
