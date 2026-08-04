"""A feature is on when it is configured, and off otherwise.

Separate enable-flags could disagree with the configuration they gate, and only
ever in one direction that matters: a flag saying yes over credentials that are
absent, which produces a subsystem that starts, fails, and says nothing.

So the flags are gone and activation is derived from what is configured.
"""

from __future__ import annotations

import pytest
from app.core.config import McpSettings, WebApiSettings

pytestmark = pytest.mark.unit


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
