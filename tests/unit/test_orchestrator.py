"""Unit tests for channel orchestrator."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.channel.config import ChannelAgentSettings, ChannelConfig
from app.agent.channel.orchestrator import (
    ChannelOrchestrator,
    SingleChannelOrchestrator,
    _next_scheduled_time,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def channel_config() -> ChannelConfig:
    return ChannelConfig(
        channel_id=-1001234567890,
        review_chat_id=-1009999999999,
        language="en",
        max_posts_per_day=3,
    )


@pytest.fixture
def agent_settings() -> ChannelAgentSettings:
    return ChannelAgentSettings(
        enabled=True,
        channel_id=-1001234567890,
        review_chat_id=0,
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
    channel_config: ChannelConfig,
    mock_session_maker: MagicMock,
) -> SingleChannelOrchestrator:
    return SingleChannelOrchestrator(
        bot=mock_bot,
        config=agent_settings,
        channel_config=channel_config,
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
    @pytest.mark.asyncio
    async def test_start_creates_task(self, single_orch: SingleChannelOrchestrator):
        with patch.object(single_orch, "_run_loop", new_callable=AsyncMock) as mock_loop:
            mock_loop.return_value = None
            single_orch.start()
            assert single_orch._task is not None
            # Cleanup
            single_orch._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await single_orch._task

    def test_start_no_channel_id_is_noop(
        self,
        mock_bot: AsyncMock,
        agent_settings: ChannelAgentSettings,
        mock_session_maker: MagicMock,
    ):
        config = ChannelConfig(channel_id=0, language="en")
        orch = SingleChannelOrchestrator(
            bot=mock_bot,
            config=agent_settings,
            channel_config=config,
            api_key="test-key",
            session_maker=mock_session_maker,
        )
        orch.start()
        assert orch._task is None

    @pytest.mark.asyncio
    async def test_stop_cancels_running_task(self, single_orch: SingleChannelOrchestrator):
        # Create a task that sleeps forever
        async def forever():
            await asyncio.sleep(3600)

        single_orch._task = asyncio.create_task(forever())  # type: ignore[no-untyped-call]
        assert not single_orch._task.done()

        await single_orch.stop()
        assert single_orch._task.done()

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_safe(self, single_orch: SingleChannelOrchestrator):
        assert single_orch._task is None
        await single_orch.stop()  # Should not raise

    def test_maybe_reset_daily_counter_resets_on_new_day(self, single_orch: SingleChannelOrchestrator):
        single_orch._posts_today = 5
        single_orch._last_reset = datetime.now(UTC) - timedelta(days=1)
        single_orch._maybe_reset_daily_counter()
        assert single_orch._posts_today == 0

    def test_maybe_reset_daily_counter_no_reset_same_day(self, single_orch: SingleChannelOrchestrator):
        single_orch._posts_today = 2
        single_orch._last_reset = datetime.now(UTC)
        single_orch._maybe_reset_daily_counter()
        assert single_orch._posts_today == 2

    def test_language_name_known_codes(self, single_orch: SingleChannelOrchestrator):
        single_orch.channel_config.language = "ru"
        assert single_orch._language_name() == "Russian"

        single_orch.channel_config.language = "cs"
        assert single_orch._language_name() == "Czech"

        single_orch.channel_config.language = "en"
        assert single_orch._language_name() == "English"

    def test_language_name_unknown_falls_back(self, single_orch: SingleChannelOrchestrator):
        single_orch.channel_config.language = "de"
        assert single_orch._language_name() == "de"

    @pytest.mark.asyncio
    async def test_run_cycle_respects_daily_limit(self, single_orch: SingleChannelOrchestrator):
        single_orch._posts_today = single_orch.channel_config.max_posts_per_day
        # _run_cycle_burr should NOT be called
        with patch.object(single_orch, "_run_cycle_burr", new_callable=AsyncMock) as mock_burr:
            await single_orch._run_cycle()
            mock_burr.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_review_no_pending_returns_message(self, single_orch: SingleChannelOrchestrator):
        result = await single_orch.resume_review(post_id=999, decision="approved")
        assert result == "No pending review found for this post."

    @pytest.mark.asyncio
    async def test_resume_review_approved_increments_posts(self, single_orch: SingleChannelOrchestrator):
        single_orch._pending_reviews[42] = {"post_id": 42, "some_state": "value"}
        single_orch._posts_today = 0

        mock_state = MagicMock()
        mock_state.get.side_effect = lambda key, default="": {
            "result_message": "Published! (msg #42)",
        }.get(key, default)
        mock_state.get_all.return_value = {}

        mock_action = MagicMock()
        mock_action.name = "done"

        mock_app = AsyncMock()
        mock_app.arun = AsyncMock(return_value=(mock_action, {}, mock_state))

        with patch("app.agent.channel.orchestrator.SingleChannelOrchestrator.resume_review") as _:
            # Test the actual method logic directly
            pass

        # Test more directly by patching the workflow import
        with patch("app.agent.channel.workflow.create_pipeline_app", return_value=mock_app):
            single_orch._pending_reviews[42] = {"post_id": 42}
            result = await single_orch.resume_review(post_id=42, decision="approved")
            assert "Published" in result
            assert single_orch._posts_today == 1

    @pytest.mark.asyncio
    async def test_maybe_discover_sources_disabled_is_noop(self, single_orch: SingleChannelOrchestrator):
        single_orch.config.source_discovery_enabled = False
        with patch("app.agent.channel.orchestrator.discover_and_add_sources", new_callable=AsyncMock) as mock_disc:
            await single_orch._maybe_discover_sources()
            mock_disc.assert_not_called()

    @pytest.mark.asyncio
    async def test_maybe_discover_sources_respects_cooldown(self, single_orch: SingleChannelOrchestrator):
        single_orch.config.source_discovery_enabled = True
        single_orch.config.source_discovery_interval_hours = 24
        # Set last discovery to just now
        single_orch._last_source_discovery = datetime.now(UTC)
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
        settings = ChannelAgentSettings(
            enabled=False,
            channels=[ChannelConfig(channel_id=-100123)],
        )
        orch = ChannelOrchestrator(bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)
        # Patch each sub-orchestrator's start to track calls
        for sub in orch.orchestrators:
            sub.start = MagicMock()  # type: ignore[method-assign]
        orch.start()
        for sub in orch.orchestrators:
            sub.start.assert_not_called()  # type: ignore[attr-defined]

    def test_no_channels_start_is_noop(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(enabled=True, channel_id=0, channels=[])
        orch = ChannelOrchestrator(bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)
        # Should not raise, just log warning
        orch.start()
        assert len(orch.orchestrators) == 0

    @pytest.mark.asyncio
    async def test_stop_stops_all(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(
            enabled=True,
            channels=[
                ChannelConfig(channel_id=-100111),
                ChannelConfig(channel_id=-100222),
            ],
        )
        orch = ChannelOrchestrator(bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)
        for sub in orch._orchestrators:
            sub.stop = AsyncMock()  # type: ignore[method-assign]
        await orch.stop()
        for sub in orch._orchestrators:
            sub.stop.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_run_once_specific_channel(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(
            enabled=True,
            channels=[
                ChannelConfig(channel_id=-100111),
                ChannelConfig(channel_id=-100222),
            ],
        )
        orch = ChannelOrchestrator(bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)
        for sub in orch._orchestrators:
            sub.run_once = AsyncMock()  # type: ignore[method-assign]
        await orch.run_once(channel_id=-100222)
        # Only the matching channel should run
        orch._orchestrators[0].run_once.assert_not_awaited()  # type: ignore[attr-defined]
        orch._orchestrators[1].run_once.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_run_once_unknown_channel_warns(
        self,
        mock_bot: AsyncMock,
        mock_session_maker: MagicMock,
    ):
        settings = ChannelAgentSettings(
            enabled=True,
            channels=[ChannelConfig(channel_id=-100111)],
        )
        orch = ChannelOrchestrator(bot=mock_bot, config=settings, api_key="k", session_maker=mock_session_maker)
        for sub in orch._orchestrators:
            sub.run_once = AsyncMock()  # type: ignore[method-assign]
        # Should not raise, just warn and return
        await orch.run_once(channel_id=-999999)
        orch._orchestrators[0].run_once.assert_not_awaited()  # type: ignore[attr-defined]
