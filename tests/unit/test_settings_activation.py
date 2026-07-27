"""A feature is on when it is configured, and off otherwise.

Separate enable-flags could disagree with the configuration they gate, and only
ever in one direction that matters: a flag saying yes over credentials that are
absent. `TELETHON_ENABLED=true` without an api_id produced a userbot that
started, failed, and said nothing.

So the flags are gone and activation is derived. The exception is moderation,
which has no credential of its own to derive from and is the one thing you may
need to switch off in a hurry.
"""

from __future__ import annotations

import pytest
from app.core.config import McpSettings, SponsoredAdsSettings, TelethonSettings, WebApiSettings

pytestmark = pytest.mark.unit


class TestTelethon:
    def test_credentials_switch_it_on(self) -> None:
        assert TelethonSettings(api_id=123, api_hash="hash").active is True

    @pytest.mark.parametrize(
        ("api_id", "api_hash", "case"),
        [
            (0, "hash", "no api_id"),
            (123, "", "no api_hash"),
            (0, "", "neither"),
        ],
    )
    def test_missing_credentials_switch_it_off(self, api_id, api_hash, case) -> None:
        assert TelethonSettings(api_id=api_id, api_hash=api_hash).active is False, case

    def test_the_session_name_is_not_configurable(self) -> None:
        """Compose mounts the session file by a fixed path.

        A configurable name would let the two disagree, and Telethon answers a
        missing session by quietly starting an unauthorised one.
        """
        assert not hasattr(TelethonSettings(), "session_name") or TelethonSettings().session_name == "moderator_userbot"


class TestMcp:
    def test_a_token_switches_it_on(self) -> None:
        assert McpSettings(token="t").active is True

    def test_no_token_leaves_it_closed(self) -> None:
        """Failing closed is the whole design; there is no second switch."""
        assert McpSettings(token="").active is False

    def test_the_path_and_port_are_not_configurable(self) -> None:
        """The compose port mapping hard-codes the container side.

        A configurable port bound the app to one number while the mapping
        forwarded to another, which cannot work in any non-default combination.
        """
        settings = McpSettings(token="t")
        assert settings.path == "/api/mcp"
        assert settings.port == 8788


class TestSponsoredAds:
    def test_a_moderator_chat_switches_it_on(self) -> None:
        assert SponsoredAdsSettings(moderator_chat_id=-100).active is True

    def test_without_a_moderator_chat_there_is_nowhere_to_alert(self) -> None:
        assert SponsoredAdsSettings(moderator_chat_id=0).active is False


class TestWebApi:
    def test_origins_come_from_the_public_url(self) -> None:
        """Two settings obliged to agree are one setting and a bug waiting."""
        settings = WebApiSettings(public_url="https://admin.example.com")

        assert settings.allowed_origins == ["https://admin.example.com"]

    def test_no_public_url_means_no_origins(self) -> None:
        """Local development supplies its own fallback rather than a wrong guess."""
        assert WebApiSettings(public_url="").allowed_origins == []

    def test_a_trailing_slash_does_not_become_a_different_origin(self) -> None:
        """Browsers compare origins exactly; the slash would fail every check."""
        settings = WebApiSettings(public_url="https://admin.example.com/")

        assert settings.allowed_origins == ["https://admin.example.com"]

    def test_secure_cookies_are_the_default(self) -> None:
        """Local development opts out; production cannot forget to opt in."""
        assert WebApiSettings().session_cookie_secure is True
