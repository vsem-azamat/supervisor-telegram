"""Channel content orchestrator — coordinates the full pipeline.

Reads channel definitions from the DB ``channels`` table (not env vars).
Each enabled channel gets a ``SingleChannelOrchestrator`` that runs
its own content loop. The top-level ``ChannelOrchestrator`` refreshes
the active channel set periodically so changes take effect without restart.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.agent.channel.channel_repo import (
    get_active_channels,
    reset_daily_count_if_needed,
    try_reserve_daily_slot,
    update_source_discovery_time,
)
from app.agent.channel.source_discovery import discover_and_add_sources
from app.core.logging import get_logger
from app.core.time import utc_now

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.config import ChannelAgentSettings
    from app.infrastructure.db.models import Channel

logger = get_logger("channel.orchestrator")


def _next_scheduled_time(schedule: list[str], now: datetime | None = None) -> datetime:
    """Find the next scheduled time from a list of ``HH:MM`` strings (UTC)."""
    if not schedule:
        raise ValueError("schedule must not be empty")

    if now is None:
        now = utc_now()

    parsed: list[tuple[int, int]] = []
    for entry in schedule:
        parts = entry.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid schedule entry: {entry!r}")
        parsed.append((int(parts[0]), int(parts[1])))

    parsed.sort()

    for hour, minute in parsed:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate

    first_h, first_m = parsed[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=first_h, minute=first_m, second=0, microsecond=0)


class SingleChannelOrchestrator:
    """Orchestrates the content pipeline for a single channel (DB-backed)."""

    def __init__(
        self,
        publish_bot: Bot,
        config: ChannelAgentSettings,
        channel: Channel,
        api_key: str,
        session_maker: async_sessionmaker[AsyncSession],
        *,
        review_bot: Bot | None = None,
    ) -> None:
        self.publish_bot = publish_bot
        self.review_bot = review_bot or publish_bot
        self.config = config
        self.channel = channel
        self.api_key = api_key
        self.session_maker = session_maker
        self._task: asyncio.Task[None] | None = None
        self._pending_reviews: dict[int, dict[str, object]] = {}

    @property
    def bot(self) -> Bot:
        """Backward-compat alias — returns the publish bot."""
        return self.publish_bot

    @property
    def channel_id(self) -> str:
        return self.channel.telegram_id

    def start(self) -> None:
        """Start the background content loop."""
        if not self.channel.telegram_id:
            logger.warning("channel_agent_no_channel_id")
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "single_channel_agent_started",
            channel_id=self.channel.telegram_id,
            name=self.channel.name,
            schedule=self.channel.posting_schedule or "interval",
            interval_min=self.config.fetch_interval_minutes,
        )

    async def stop(self) -> None:
        """Stop the background loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("single_channel_agent_stopped", channel_id=self.channel.telegram_id)

    async def _run_loop(self) -> None:
        """Main loop: discover sources, fetch content, screen, generate, send for review."""
        await asyncio.sleep(5)

        while True:
            try:
                await self._maybe_discover_sources()
                await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("channel_cycle_error", channel_id=self.channel.telegram_id)

            await self._sleep_until_next()

    async def _sleep_until_next(self) -> None:
        """Sleep until the next posting time (schedule or interval)."""
        schedule = self.channel.posting_schedule
        if schedule:
            now = utc_now()
            next_time = _next_scheduled_time(schedule, now)
            delay = (next_time - now).total_seconds()
            logger.info(
                "sleeping_until_scheduled",
                channel_id=self.channel.telegram_id,
                next_time=next_time.isoformat(),
                delay_seconds=int(delay),
            )
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(self.config.fetch_interval_minutes * 60)

    async def _maybe_discover_sources(self) -> None:
        """Run source discovery if enough time has passed (persisted in DB)."""
        if not self.config.source_discovery_enabled:
            return

        interval = self.config.source_discovery_interval_hours * 3600
        last = self.channel.last_source_discovery_at
        if last and (utc_now() - last).total_seconds() < interval:
            return

        query = self.channel.source_discovery_query or self.config.source_discovery_query
        logger.info("source_discovery_start", query=query[:60])
        added = await discover_and_add_sources(
            api_key=self.api_key,
            channel_id=self.channel.telegram_id,
            query=query,
            session_maker=self.session_maker,
            model=self.config.discovery_model,
            http_timeout=self.config.http_timeout,
            temperature=self.config.temperature,
        )
        await update_source_discovery_time(self.session_maker, self.channel.telegram_id)
        # Refresh in-memory reference
        self.channel.last_source_discovery_at = utc_now()
        logger.info("source_discovery_done", added=added)

    async def _run_cycle(self) -> None:
        """Run one full pipeline cycle."""
        await reset_daily_count_if_needed(self.session_maker, self.channel.telegram_id)

        # Re-read daily count from DB (persisted across restarts)
        from app.agent.channel.channel_repo import get_channel_by_telegram_id

        refreshed = await get_channel_by_telegram_id(self.session_maker, self.channel.telegram_id)
        if refreshed:
            self.channel.daily_posts_count = refreshed.daily_posts_count
            self.channel.daily_count_date = refreshed.daily_count_date

        if not self.channel.can_post_today:
            logger.info(
                "daily_post_limit_reached",
                count=self.channel.daily_posts_count,
                channel_id=self.channel.telegram_id,
            )
            return

        await self._run_cycle_burr()

    async def _run_cycle_burr(self) -> None:
        """Run the pipeline via a Burr state-machine workflow."""
        from app.agent.channel.workflow import create_pipeline_app

        channel_id = self.channel.telegram_id
        app = create_pipeline_app(
            channel_id=channel_id,
            session_maker=self.session_maker,
            publish_bot=self.publish_bot,
            review_bot=self.review_bot,
            api_key=self.api_key,
            config=self.config,
            channel=self.channel,
            app_id=f"pipeline-{channel_id}",
        )

        _action, _result, state = await app.arun(
            halt_after=["await_review", "done"],
        )

        post_id = state.get("post_id")
        if _action and _action.name == "await_review" and post_id:
            self._pending_reviews[post_id] = state.get_all()
            logger.info("workflow_halted_for_review", post_id=post_id, channel_id=channel_id)
        elif state.get("result_message", "").startswith("published_directly:"):
            await try_reserve_daily_slot(self.session_maker, channel_id)

    async def resume_review(self, post_id: int, decision: str) -> str:
        """Resume a halted Burr workflow after admin review."""
        from app.agent.channel.workflow import create_pipeline_app

        saved_state = self._pending_reviews.pop(post_id, None)
        if not saved_state:
            logger.warning("no_pending_review", post_id=post_id)
            return "No pending review found for this post."

        saved_state["review_decision"] = decision

        channel_id = self.channel.telegram_id
        app = create_pipeline_app(
            channel_id=channel_id,
            session_maker=self.session_maker,
            publish_bot=self.publish_bot,
            review_bot=self.review_bot,
            api_key=self.api_key,
            config=self.config,
            channel=self.channel,
            app_id=f"pipeline-{channel_id}-review-{post_id}",
            resume_state=dict(saved_state),
            entrypoint="await_review",
        )

        _action, _result, state = await app.arun(halt_after=["done"])

        result_message = state.get("result_message", "")
        # NOTE: do NOT increment_daily_count here — approve_post() already does it
        logger.info("workflow_review_complete", post_id=post_id, decision=decision, result=result_message)
        return result_message

    async def run_once(self) -> None:
        """Run a single cycle manually (for testing or command trigger)."""
        await self._run_cycle()


class ChannelOrchestrator:
    """Manages multiple ``SingleChannelOrchestrator`` instances from the DB."""

    def __init__(
        self,
        publish_bot: Bot,
        config: ChannelAgentSettings,
        api_key: str,
        session_maker: async_sessionmaker[AsyncSession],
        *,
        review_bot: Bot | None = None,
    ) -> None:
        self.publish_bot = publish_bot
        self.review_bot = review_bot or publish_bot
        self.config = config
        self.api_key = api_key
        self.session_maker = session_maker
        self._orchestrators: dict[str, SingleChannelOrchestrator] = {}
        self._refresh_task: asyncio.Task[None] | None = None

    @property
    def bot(self) -> Bot:
        """Backward-compat alias — returns the publish bot."""
        return self.publish_bot

    @property
    def orchestrators(self) -> list[SingleChannelOrchestrator]:
        return list(self._orchestrators.values())

    def start(self) -> None:
        """Start a background task that refreshes channels from DB and runs them."""
        if not self.config.enabled:
            logger.info("channel_agent_disabled")
            return
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("channel_orchestrator_started")

    async def _refresh_loop(self) -> None:
        """Periodically refresh active channels from DB and manage sub-orchestrators."""
        # On first run, recover orphaned reviews from DB
        await self._recover_orphaned_reviews()

        while True:
            try:
                await self._refresh_channels()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("channel_refresh_error")
            await asyncio.sleep(300)  # Re-check DB every 5 minutes

    async def _refresh_channels(self) -> None:
        """Sync running orchestrators with DB state."""
        db_channels = await get_active_channels(self.session_maker)
        db_ids = {ch.telegram_id for ch in db_channels}

        # Stop orchestrators for removed/disabled channels
        for tid in list(self._orchestrators):
            if tid not in db_ids:
                await self._orchestrators[tid].stop()
                del self._orchestrators[tid]
                logger.info("channel_removed", channel_id=tid)

        # Start new or update existing orchestrators
        for ch in db_channels:
            if ch.telegram_id in self._orchestrators:
                # Update the channel reference so config/schedule changes propagate
                existing = self._orchestrators[ch.telegram_id]
                existing.channel = ch
            else:
                orch = SingleChannelOrchestrator(
                    publish_bot=self.publish_bot,
                    config=self.config,
                    channel=ch,
                    api_key=self.api_key,
                    session_maker=self.session_maker,
                    review_bot=self.review_bot,
                )
                self._orchestrators[ch.telegram_id] = orch
                orch.start()
                logger.info("channel_added", channel_id=ch.telegram_id, name=ch.name)

    async def _recover_orphaned_reviews(self) -> None:
        """Scan DB for draft posts with review_message_id and load into pending reviews.

        This handles the case where the bot restarted while reviews were pending.
        """
        from sqlalchemy import select

        from app.domain.value_objects import PostStatus
        from app.infrastructure.db.models import ChannelPost

        try:
            async with self.session_maker() as session:
                result = await session.execute(
                    select(ChannelPost).where(
                        ChannelPost.status == PostStatus.DRAFT,
                        ChannelPost.review_message_id.isnot(None),
                    )
                )
                orphans = list(result.scalars().all())

            if not orphans:
                return

            # Ensure orchestrators are loaded so we can attach reviews
            await self._refresh_channels()

            recovered = 0
            for post in orphans:
                orch = self._orchestrators.get(post.channel_id)
                if orch and post.id not in orch._pending_reviews:
                    orch._pending_reviews[post.id] = {
                        "channel_id": post.channel_id,
                        "post_id": post.id,
                        "review_decision": None,
                    }
                    recovered += 1

            if recovered:
                logger.info("orphaned_reviews_recovered", count=recovered, total_orphans=len(orphans))
        except Exception:
            logger.exception("orphaned_review_recovery_failed")

    async def stop(self) -> None:
        """Stop all sub-orchestrators."""
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
        for orch in self._orchestrators.values():
            await orch.stop()
        logger.info("channel_orchestrator_stopped")

    async def run_once(self, channel_id: int | str | None = None) -> None:
        """Run a single cycle for a specific channel, or all channels."""
        if not self._orchestrators:
            await self._refresh_channels()

        targets = list(self._orchestrators.values())
        if channel_id is not None:
            cid = str(channel_id)
            targets = [o for o in targets if o.channel_id == cid]
            if not targets:
                logger.warning("run_once_channel_not_found", channel_id=channel_id)
                return
        for orch in targets:
            await orch.run_once()
