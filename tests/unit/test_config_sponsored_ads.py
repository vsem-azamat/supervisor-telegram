import pytest
from app.core.config import SponsoredAdsSettings


def test_sponsored_ads_settings_defaults() -> None:
    s = SponsoredAdsSettings()
    assert s.moderator_chat_id == 0
    assert s.sales_contact == ""
    # No moderator chat means nowhere to send an alert, which is what "off" is.
    assert s.active is False


def test_sponsored_ads_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPONSORED_ADS_MODERATOR_CHAT_ID", "-1009999")
    monkeypatch.setenv("SPONSORED_ADS_SALES_CONTACT", "@konnekt_ads")
    s = SponsoredAdsSettings()
    assert s.moderator_chat_id == -1009999
    assert s.sales_contact == "@konnekt_ads"
    assert s.active is True
