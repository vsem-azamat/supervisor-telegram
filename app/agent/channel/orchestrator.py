"""Channel content orchestrator — coordinates the full pipeline.

Reads channel definitions from the DB ``channels`` table (not env vars).
Each enabled channel gets a ``SingleChannelOrchestrator`` that runs
its own content loop. The top-level ``ChannelOrchestrator`` refreshes
the active channel set periodically so changes take effect without restart.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.agent.channel.channel_repo import (
    get_active_channels,
    increment_daily_count,
    reset_daily_count_if_needed,
    update_source_discovery_time,
)
from app.agent.channel.discovery import discover_content
from app.agent.channel.feedback import get_feedback_summary
from app.agent.channel.generator import generate_post, screen_items
from app.agent.channel.review import send_for_review
from app.agent.channel.source_discovery import discover_and_add_sources
from app.agent.channel.source_manager import (
    get_active_sources,
    record_fetch_error,
    record_fetch_success,
    seed_sources_from_env,
)
from app.agent.channel.sources import fetch_all_sources
from app.core.logging import get_logger
from app.infrastructure.db.models import Channel, ChannelPost

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.config import ChannelAgentSettings

logger = get_logger("channel.orchestrator")


def _next_scheduled_time(schedule: list[str], now: datetime | None = None) -> datetime:
    """Find the next scheduled time from a list of ``HH:MM`` strings (UTC)."""
    if not schedule:
        raise ValueError("schedule must not be empty")

    if now is None:
        now = datetime.now(UTC)

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
        bot: Bot,
        config: ChannelAgentSettings,
        channel: Channel,
        api_key: str,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self.bot = bot
        self.config = config
        self.channel = channel
        self.api_key = api_key
        self.session_maker = session_maker
        self._seen_ids: dict[str, None] = {}
        self._task: asyncio.Task[None] | None = None
        self._pending_reviews: dict[int, dict[str, object]] = {}

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

        # Seed DB sources from env config on first run (deprecated, for migration)
        if self.config.rss_source_list:
            await seed_sources_from_env(
                self.session_maker,
                self.channel.telegram_id,
                self.config.rss_source_list,
            )

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
            now = datetime.now(UTC)
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
        if last and (datetime.now(UTC) - last).total_seconds() < interval:
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
        self.channel.last_source_discovery_at = datetime.now(UTC)
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

        try:
            await self._run_cycle_burr()
        except Exception:
            logger.exception("burr_workflow_error_falling_back", channel_id=self.channel.telegram_id)
            await self._run_cycle_legacy()

    async def _run_cycle_burr(self) -> None:
        """Run the pipeline via a Burr state-machine workflow."""
        from app.agent.channel.workflow import create_pipeline_app

        channel_id = self.channel.telegram_id
        app = create_pipeline_app(
            channel_id=channel_id,
            session_maker=self.session_maker,
            bot=self.bot,
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
            await increment_daily_count(self.session_maker, channel_id)

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
            bot=self.bot,
            api_key=self.api_key,
            config=self.config,
            channel=self.channel,
            app_id=f"pipeline-{channel_id}-review-{post_id}",
            resume_state=dict(saved_state),
            entrypoint="await_review",
        )

        _action, _result, state = await app.arun(halt_after=["done"])

        result_message = state.get("result_message", "")
        if decision == "approved" and "Published" in result_message:
            await increment_daily_count(self.session_maker, channel_id)
        logger.info("workflow_review_complete", post_id=post_id, decision=decision, result=result_message)
        return result_message

    async def _run_cycle_legacy(self) -> None:
        """Legacy inline pipeline (fallback if Burr is unavailable)."""
        channel_id = self.channel.telegram_id

        # 1. Gather content from all sources
        all_items = []

        # 1a. Fetch from DB-registered RSS sources
        db_sources = await get_active_sources(self.session_maker, channel_id)
        if db_sources:
            rss_urls = [s.url for s in db_sources]
            logger.info("fetching_rss_sources", count=len(rss_urls))
            fetch_result = await fetch_all_sources(rss_urls, http_timeout=self.config.http_timeout)
            all_items.extend(fetch_result.items)

            for url in fetch_result.successful_urls:
                await record_fetch_success(self.session_maker, url)
            for url in fetch_result.errored_urls:
                await record_fetch_error(self.session_maker, url, "fetch_error")

        # 1b. Discover fresh content via Perplexity Sonar
        if self.config.discovery_enabled:
            query = self.channel.discovery_query or self.config.discovery_query
            logger.info("discovering_content", query=query[:60])
            discovered = await discover_content(
                api_key=self.api_key,
                query=query,
                model=self.config.discovery_model,
                http_timeout=self.config.http_timeout,
                temperature=self.config.temperature,
            )
            all_items.extend(discovered)

        # Deduplicate: in-memory cache as fast first pass, then DB as source of truth
        candidates = [i for i in all_items if i.external_id not in self._seen_ids]
        if candidates:
            from sqlalchemy import select

            async with self.session_maker() as session:
                existing_ext_ids_result = await session.execute(
                    select(ChannelPost.external_id).where(
                        ChannelPost.channel_id == channel_id,
                        ChannelPost.external_id.in_([i.external_id for i in candidates]),
                    )
                )
                existing_ext_ids = set(existing_ext_ids_result.scalars().all())
            new_items = [i for i in candidates if i.external_id not in existing_ext_ids]
        else:
            new_items = []

        for item in new_items:
            self._seen_ids[item.external_id] = None
        while len(self._seen_ids) > 10000:
            self._seen_ids.pop(next(iter(self._seen_ids)))

        if not new_items:
            logger.info("no_new_content")
            return

        # Semantic dedup — filter items similar to recent posts (cross-source)
        try:
            from app.agent.channel.semantic_dedup import filter_semantic_duplicates

            new_items = await filter_semantic_duplicates(
                new_items,
                channel_id=channel_id,
                api_key=self.api_key,
                session_maker=self.session_maker,
                model=self.config.embedding_model,
                dimensions=self.config.embedding_dimensions,
                threshold=self.config.semantic_dedup_threshold,
            )
        except Exception:
            logger.exception("semantic_dedup_error_skipping", channel_id=channel_id)

        if not new_items:
            logger.info("no_new_content_after_semantic_dedup")
            return

        logger.info("new_items_found", count=len(new_items))

        # 2. Screen for relevance
        relevant = await screen_items(
            new_items,
            api_key=self.api_key,
            model=self.config.screening_model,
            threshold=self.config.screening_threshold,
        )

        if not relevant:
            logger.info("no_relevant_items")
            return

        logger.info("relevant_items", count=len(relevant))

        # 3. Fetch admin feedback context
        feedback_context: str | None = None
        try:
            feedback_context = await get_feedback_summary(
                session_maker=self.session_maker,
                channel_id=channel_id,
                api_key=self.api_key,
                model=self.config.screening_model,
                http_timeout=self.config.http_timeout,
                temperature=self.config.temperature,
            )
            if feedback_context:
                logger.info("feedback_context_loaded", length=len(feedback_context))
        except Exception:
            logger.exception("feedback_context_error")

        # 4. Generate post
        from app.agent.channel.config import language_name

        language = language_name(self.channel.language)
        post = await generate_post(
            relevant[:1],
            api_key=self.api_key,
            model=self.config.generation_model,
            language=language,
            feedback_context=feedback_context,
        )

        if not post:
            logger.warning("post_generation_failed")
            return

        # 5. Send for review (or direct publish if no review channel)
        review_chat_id = self.channel.review_chat_id
        if review_chat_id:
            post_id = await send_for_review(
                bot=self.bot,
                review_chat_id=review_chat_id,
                channel_id=channel_id,
                post=post,
                source_items=relevant[:1],
                session_maker=self.session_maker,
            )
            if post_id:
                logger.info("draft_sent_for_review", post_id=post_id)
        else:
            from app.agent.channel.publisher import publish_post

            msg_id = await publish_post(self.bot, self.channel.telegram_id, post)
            if msg_id:
                await increment_daily_count(self.session_maker, channel_id)

    async def run_once(self) -> None:
        """Run a single cycle manually (for testing or command trigger)."""
        await self._run_cycle()


class ChannelOrchestrator:
    """Manages multiple ``SingleChannelOrchestrator`` instances from the DB."""

    def __init__(
        self,
        bot: Bot,
        config: ChannelAgentSettings,
        api_key: str,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self.bot = bot
        self.config = config
        self.api_key = api_key
        self.session_maker = session_maker
        self._orchestrators: dict[str, SingleChannelOrchestrator] = {}

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

        # Start orchestrators for new channels
        for ch in db_channels:
            if ch.telegram_id not in self._orchestrators:
                orch = SingleChannelOrchestrator(
                    bot=self.bot,
                    config=self.config,
                    channel=ch,
                    api_key=self.api_key,
                    session_maker=self.session_maker,
                )
                self._orchestrators[ch.telegram_id] = orch
                orch.start()
                logger.info("channel_added", channel_id=ch.telegram_id, name=ch.name)

    async def stop(self) -> None:
        """Stop all sub-orchestrators."""
        if hasattr(self, "_refresh_task") and not self._refresh_task.done():
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
