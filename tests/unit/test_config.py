"""Unit tests for configuration classes, container, and two-bot wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.core.config import ModerationSettings, TelethonSettings

# ---------------------------------------------------------------------------
# ModerationSettings validation
# ---------------------------------------------------------------------------


class TestModerationSettingsValidation:
    def test_valid_timeout_actions(self):
        for action in ("mute", "ban", "delete", "warn", "blacklist", "escalate", "ignore"):
            s = ModerationSettings(default_timeout_action=action)
            assert s.default_timeout_action == action

    def test_invalid_timeout_action_raises(self):
        with pytest.raises(ValueError, match="default_timeout_action must be one of"):
            ModerationSettings(default_timeout_action="nuke")

    def test_invalid_timeout_action_empty_raises(self):
        with pytest.raises(ValueError, match="default_timeout_action must be one of"):
            ModerationSettings(default_timeout_action="")


# ---------------------------------------------------------------------------
# Container.try_get_bot
# ---------------------------------------------------------------------------


class TestContainerTryGetBot:
    def test_returns_none_when_not_set(self):
        from app.core.container import Container

        c = Container()
        assert c.try_get_bot() is None

    def test_returns_bot_when_set(self):
        from app.core.container import Container

        c = Container()
        bot = MagicMock()
        c.set_bot(bot)
        assert c.try_get_bot() is bot

    def test_get_bot_raises_when_not_set(self):
        from app.core.container import Container

        c = Container()
        with pytest.raises(ValueError, match="Bot not set"):
            c.get_bot()


def test_init_telethon_wires_client_without_enabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.container import container
    from app.presentation.telegram import bot as telegram_bot

    monkeypatch.setattr(container, "_telethon_client", None, raising=False)
    monkeypatch.setattr(
        telegram_bot.settings,
        "telethon",
        TelethonSettings(api_id=1, api_hash="hash", session_name="test_session", phone=None),
    )

    client = telegram_bot._init_telethon()

    assert client is not None
    assert container.get_telethon_client() is client
