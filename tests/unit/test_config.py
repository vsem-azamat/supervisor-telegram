"""Unit tests for configuration classes, container, and two-bot wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# Two-bot orchestrator wiring
# ---------------------------------------------------------------------------


class TestTwoBotOrchestrator:
    def test_review_bot_defaults_to_publish_bot(self):
        from app.agent.channel.config import ChannelAgentSettings
        from app.agent.channel.orchestrator import SingleChannelOrchestrator
        from app.infrastructure.db.models import Channel

        bot = AsyncMock()
        ch = Channel(telegram_id="-100123", name="Test", language="en")  # type: ignore[call-arg]
        orch = SingleChannelOrchestrator(
            publish_bot=bot,
            config=ChannelAgentSettings(enabled=True),
            channel=ch,
            api_key="k",
            session_maker=MagicMock(),
        )
        assert orch.review_bot is bot
        assert orch.publish_bot is bot

    def test_separate_review_bot(self):
        from app.agent.channel.config import ChannelAgentSettings
        from app.agent.channel.orchestrator import SingleChannelOrchestrator
        from app.infrastructure.db.models import Channel

        pub_bot = AsyncMock()
        rev_bot = AsyncMock()
        ch = Channel(telegram_id="-100123", name="Test", language="en")  # type: ignore[call-arg]
        orch = SingleChannelOrchestrator(
            publish_bot=pub_bot,
            config=ChannelAgentSettings(enabled=True),
            channel=ch,
            api_key="k",
            session_maker=MagicMock(),
            review_bot=rev_bot,
        )
        assert orch.review_bot is rev_bot
        assert orch.publish_bot is pub_bot
        assert orch.bot is pub_bot  # backward-compat property

    async def test_resume_review_converts_str_to_enum(self):
        from app.agent.channel.config import ChannelAgentSettings
        from app.agent.channel.orchestrator import SingleChannelOrchestrator
        from app.core.enums import ReviewDecision
        from app.infrastructure.db.models import Channel

        bot = AsyncMock()
        ch = Channel(telegram_id="-100123", name="Test", language="en")  # type: ignore[call-arg]
        orch = SingleChannelOrchestrator(
            publish_bot=bot,
            config=ChannelAgentSettings(enabled=True),
            channel=ch,
            api_key="k",
            session_maker=MagicMock(),
        )

        # Inject a pending review
        orch._pending_reviews[42] = {"channel_id": "-100123", "post_id": 42}

        # Mock create_pipeline_app to capture the resume_state
        captured_state: dict = {}

        def fake_create(**kwargs):
            captured_state.update(kwargs.get("resume_state", {}))
            mock_app = MagicMock()
            mock_app.arun = AsyncMock(return_value=(None, None, MagicMock(get=lambda _k, d="": d)))
            return mock_app

        with patch("app.agent.channel.workflow.create_pipeline_app", side_effect=fake_create):
            await orch.resume_review(42, "approved")

        assert captured_state["review_decision"] == ReviewDecision.APPROVED
        assert isinstance(captured_state["review_decision"], ReviewDecision)
