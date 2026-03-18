"""Unit tests for channel orchestrator."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.channel.config import ChannelAgentSettings
from app.agent.channel.orchestrator import (
    ChannelOrchestrator,
    SingleChannelOrchestrator,
    _next_scheduled_time,
)
from app.infrastructure.db.models import Channel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_channel(**kwargs: Any) -> Channel:
    """Create a Channel model instance without DB."""
    defaults: dict[str, Any] = {
        "telegram_id": -1001234567890,
        "name": "Test Channel",
        "description": "Test channel for unit tests",
        "language": "en",
        "review_chat_id": -1009999999999,
        "max_posts_per_day": 3,
    }
    defaults.update(kwargs)
    return Channel(**defaults)


@pytest.fixture
def channel() -> Channel:
    return _make_channel()


@pytest.fixture
def agent_settings() -> ChannelAgentSettings:
    return ChannelAgentSettings(
        enabled=True,
        discovery_enabled=False,
        source_discovery_enabled=False,
    )


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message.return_value = msg
    return bot


@pytest.fixture
def mock_session_maker() -> MagicMock:
    maker = MagicMock()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    maker.return_value = session
    maker._mock_session = session
    return maker


@pytest.fixture
def single_orch(
    mock_bot: AsyncMock,
    agent_settings: ChannelAgentSettings,
    channel: Channel,
    mock_session_maker: MagicMock,
) -> SingleChannelOrchestrator:
    return SingleChannelOrchestrator(
        publish_bot=mock_bot,
        config=agent_settings,
        channel=channel,
        api_key="test-key",
        session_maker=mock_session_maker,
    )


# ---------------------------------------------------------------------------
# _next_scheduled_time tests
# ---------------------------------------------------------------------------


class TestNextScheduledTime:
    def test_next_time_today(self):
        now = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        result = _next_scheduled_time(["09:00", "12:00", "18:00"], now)
        assert result == datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

    def test_next_time_tomorrow(self):
        now = datetime(2025, 1, 1, 19, 0, tzinfo=UTC)
        result = _next_scheduled_time(["09:00", "12:00", "18:00"], now)
        assert result == datetime(2025, 1, 2, 9, 0, tzinfo=UTC)

    def test_next_time_single_entry(self):
        now = datetime(2025, 1, 1, 8, 0, tzinfo=UTC)
        result = _next_scheduled_time(["12:30"], now)
        assert result == datetime(2025, 1, 1, 12, 30, tzinfo=UTC)

    def test_empty_schedule_raises(self):
        with pytest.raises(ValueError, match="schedule must not be empty"):
            _next_scheduled_time([])

    def test_invalid_entry_raises(self):
        with pytest.raises(ValueError, match="Invalid schedule entry"):
            _next_scheduled_time(["bad"])


# ---------------------------------------------------------------------------
# SingleChannelOrchestrator tests
# ---------------------------------------------------------------------------


class TestSingleChannelOrchestrator:
    async def test_start_creates_task(self, single_orch: SingleChannelOrchestrator):
        with patch.object(single_orch, "_run_loop", new_callable=AsyncMock) as mock_loop:
            mock_loop.return_value = None
            single_orch.start()
            assert single_orch._task is not None
            single_orch._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await single_orch._task

    def test_start_no_channel_id_is_noop(
        self,
        mock_bot: AsyncMock,
        agent_settings: ChannelAgentSettings,
        mock_session_maker: MagicMock,
    ):
        ch = _make_channel(telegram_id=0)
        orch = SingleChannelOrchestrator(
            publish_bot=mock_bot,
            config=agent_settings,
            channel=ch,
            api_key="test-key",
            session_maker=mock_session_maker,
        )
        orch.start()
        assert orch._task is None

    async def test_stop_cancels_running_task(self, single_orch: SingleChannelOrchestrator):
        async def forever() -> None:
            await asyncio.sleep(3600)

        single_orch._task = asyncio.create_task(forever())
        assert not single_orch._task.done()

        await single_orch.stop()
        assert single_orch._task.done()

    async def test_stop_when_not_started_is_safe(self, single_orch: SingleChannelOrchestrator):
        assert single_orch._task is None
        await single_orch.stop()

    async def test_resume_review_no_pending_returns_message(self, single_orch: SingleChannelOrchestrator):
        result = await single_orch.resume_review(post_id=999, decision="approved")
        assert result == "No pending review found for this post."

    async def test_maybe_discover_sources_disabled_is_noop(self, single_orch: SingleChannelOrchestrator):
        single_orch.config.source_discovery_enabled = False
        with patch("app.agent.channel.orchestrator.discover_and_add_sources", new_callable=AsyncMock) as mock_disc:
            await single_orch._maybe_discover_sources()
            mock_disc.assert_not_called()

    async def test_maybe_discover_sources_respects_cooldown(self, single_orch: SingleChannelOrchestrator):
        single_orch.config.source_discovery_enabled = True
        single_orch.config.source_discovery_interval_hours = 24
        from app.core.time import utc_now

        single_orch.channel.last_source_discovery_at = utc_now()
        with patch("app.agent.channel.orchestrator.discover_and_add_sources", new_callable=AsyncMock) as mock_disc:
            await single_orch._maybe_discover_sources()
            mock_disc.assert_not_called()


# ---------------------------------------------------------------------------
# ChannelOrchestrator tests
# ---------------------------------------------------------------------------


class TestChannelOrchestrator:
    def test_disabled_start_is_noop(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(enabled=False)
        orch = ChannelOrchestrator(publish_bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)
        orch.start()
        assert len(orch.orchestrators) == 0

    async def test_refresh_starts_new_channels(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(enabled=True)
        orch = ChannelOrchestrator(publish_bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)

        ch1 = _make_channel(telegram_id=-1001111111111, name="Chan1")
        ch2 = _make_channel(telegram_id=-1002222222222, name="Chan2")

        with patch(
            "app.agent.channel.orchestrator.get_active_channels", new_callable=AsyncMock, return_value=[ch1, ch2]
        ):
            with patch.object(SingleChannelOrchestrator, "start"):
                await orch._refresh_channels()

        assert len(orch.orchestrators) == 2
        ids = sorted(o.channel_id for o in orch.orchestrators)
        assert ids == [-1002222222222, -1001111111111]

    async def test_refresh_stops_removed_channels(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(enabled=True)
        orch = ChannelOrchestrator(publish_bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)

        ch1 = _make_channel(telegram_id=-1001111111111, name="Chan1")
        ch2 = _make_channel(telegram_id=-1002222222222, name="Chan2")

        with patch(
            "app.agent.channel.orchestrator.get_active_channels", new_callable=AsyncMock, return_value=[ch1, ch2]
        ):
            with patch.object(SingleChannelOrchestrator, "start"):
                await orch._refresh_channels()

        assert len(orch.orchestrators) == 2

        # Now only ch1 is active
        for sub in orch.orchestrators:
            sub.stop = AsyncMock()  # type: ignore[method-assign]

        with patch("app.agent.channel.orchestrator.get_active_channels", new_callable=AsyncMock, return_value=[ch1]):
            await orch._refresh_channels()

        assert len(orch.orchestrators) == 1
        assert orch.orchestrators[0].channel_id == -1001111111111

    async def test_stop_stops_all(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(enabled=True)
        orch = ChannelOrchestrator(publish_bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)

        ch1 = _make_channel(telegram_id=-1001111111111, name="Chan1")

        with patch("app.agent.channel.orchestrator.get_active_channels", new_callable=AsyncMock, return_value=[ch1]):
            with patch.object(SingleChannelOrchestrator, "start"):
                await orch._refresh_channels()

        for sub in orch._orchestrators.values():
            sub.stop = AsyncMock()  # type: ignore[method-assign]

        await orch.stop()
        for sub in orch._orchestrators.values():
            sub.stop.assert_awaited_once()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Two-bot orchestrator wiring
# ---------------------------------------------------------------------------


class TestTwoBotOrchestrator:
    def test_review_bot_defaults_to_publish_bot(self):
        bot = AsyncMock()
        ch = Channel(telegram_id=-100123, name="Test", language="en")
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
        pub_bot = AsyncMock()
        rev_bot = AsyncMock()
        ch = Channel(telegram_id=-100123, name="Test", language="en")
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
        from app.core.enums import ReviewDecision

        bot = AsyncMock()
        ch = Channel(telegram_id=-100123, name="Test", language="en")
        orch = SingleChannelOrchestrator(
            publish_bot=bot,
            config=ChannelAgentSettings(enabled=True),
            channel=ch,
            api_key="k",
            session_maker=MagicMock(),
        )

        # Inject a pending review
        orch._pending_reviews[42] = {"channel_id": -100123, "post_id": 42}

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
