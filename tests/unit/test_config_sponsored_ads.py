import pytest
from app.core.config import SponsoredAdsSettings


def test_sponsored_ads_settings_defaults() -> None:
    s = SponsoredAdsSettings()
    assert s.enabled is False
    assert s.moderator_chat_id == 0
    assert s.sales_contact == ""


def test_sponsored_ads_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONSORED_ADS_ENABLED", "true")
    monkeypatch.setenv("SPONSORED_ADS_MODERATOR_CHAT_ID", "-1009999")
    monkeypatch.setenv("SPONSORED_ADS_SALES_CONTACT", "@konnekt_ads")
    s = SponsoredAdsSettings()
    assert s.enabled is True
    assert s.moderator_chat_id == -1009999
    assert s.sales_contact == "@konnekt_ads"
