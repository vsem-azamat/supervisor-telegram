"""Unit tests for configuration classes, container, and two-bot wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.core.config import ModerationSettings

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
