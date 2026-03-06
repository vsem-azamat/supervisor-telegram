"""Channel content orchestrator — coordinates the full pipeline."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

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
from app.infrastructure.db.models import ChannelPost

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.config import ChannelAgentSettings, ChannelConfig

logger = get_logger("channel.orchestrator")


def _next_scheduled_time(schedule: list[str], now: datetime | None = None) -> datetime:
    """Find the next scheduled time from a list of ``HH:MM`` strings (UTC).

    If all times for today have passed, the earliest time tomorrow is returned.

    Raises ``ValueError`` if *schedule* is empty or contains invalid entries.
    """
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

    # Sort by (hour, minute) for deterministic ordering
    parsed.sort()

    # Try to find a time later today
    for hour, minute in parsed:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate

    # All times today have passed — take the earliest time tomorrow
    first_h, first_m = parsed[0]
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=first_h, minute=first_m, second=0, microsecond=0)


class SingleChannelOrchestrator:
    """Orchestrates the content pipeline for a single channel."""

    def __init__(
        self,
        bot: Bot,
        config: ChannelAgentSettings,
        channel_config: ChannelConfig,
        api_key: str,
        session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        self.bot = bot
        self.config = config
        self.channel_config = channel_config
        self.api_key = api_key
        self.session_maker = session_maker
        self._seen_ids: dict[str, None] = {}  # ordered dict as LRU set, capped at 10k
        self._posts_today: int = 0
        self._last_reset: datetime = datetime.now(UTC)
        self._last_source_discovery: datetime | None = None
        self._task: asyncio.Task[None] | None = None
        # Burr workflow: stored halted app state keyed by post_id
        self._pending_reviews: dict[int, dict[str, object]] = {}

    @property
    def channel_id(self) -> int | str:
        return self.channel_config.channel_id

    def start(self) -> None:
        """Start the background content loop."""
        if not self.channel_config.channel_id:
            logger.warning("channel_agent_no_channel_id")
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "single_channel_agent_started",
            channel_id=self.channel_config.channel_id,
            schedule=self.channel_config.posting_schedule or "interval",
            interval_min=self.config.fetch_interval_minutes,
        )

    async def stop(self) -> None:
        """Stop the background loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("single_channel_agent_stopped", channel_id=self.channel_config.channel_id)

    async def _run_loop(self) -> None:
        """Main loop: discover sources, fetch content, screen, generate, send for review."""
        await asyncio.sleep(5)

        # Seed DB sources from env config on first run (deprecated, for migration)
        if self.config.rss_source_list:
            await seed_sources_from_env(
                self.session_maker,
                str(self.channel_config.channel_id),
                self.config.rss_source_list,
            )

        while True:
            try:
                # Source discovery (daily)
                await self._maybe_discover_sources()

                # Content pipeline
                await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("channel_cycle_error", channel_id=self.channel_config.channel_id)

            # Sleep: schedule-based or interval-based
            await self._sleep_until_next()

    async def _sleep_until_next(self) -> None:
        """Sleep until the next posting time (schedule or interval)."""
        schedule = self.channel_config.posting_schedule
        if schedule:
            now = datetime.now(UTC)
            next_time = _next_scheduled_time(schedule, now)
            delay = (next_time - now).total_seconds()
            logger.info(
                "sleeping_until_scheduled",
                channel_id=self.channel_config.channel_id,
                next_time=next_time.isoformat(),
                delay_seconds=int(delay),
            )
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(self.config.fetch_interval_minutes * 60)

    async def _maybe_discover_sources(self) -> None:
        """Run source discovery if enough time has passed."""
        if not self.config.source_discovery_enabled:
            return

        now = datetime.now(UTC)
        interval = self.config.source_discovery_interval_hours * 3600

        if self._last_source_discovery and (now - self._last_source_discovery).total_seconds() < interval:
            return

        query = self.channel_config.source_discovery_query or self.config.source_discovery_query
        logger.info("source_discovery_start", query=query[:60])
        added = await discover_and_add_sources(
            api_key=self.api_key,
            channel_id=str(self.channel_config.channel_id),
            query=query,
            session_maker=self.session_maker,
            model=self.config.discovery_model,
        )
        self._last_source_discovery = now
        logger.info("source_discovery_done", added=added)

    async def _run_cycle(self) -> None:
        """Run one full pipeline cycle.

        Delegates to the Burr state-machine workflow when available, falling
        back to the legacy inline implementation otherwise.
        """
        self._maybe_reset_daily_counter()

        max_posts = self.channel_config.max_posts_per_day
        if self._posts_today >= max_posts:
            logger.info("daily_post_limit_reached", count=self._posts_today, channel_id=self.channel_config.channel_id)
            return

        try:
            await self._run_cycle_burr()
        except Exception:
            logger.exception("burr_workflow_error_falling_back", channel_id=self.channel_config.channel_id)
            await self._run_cycle_legacy()

    async def _run_cycle_burr(self) -> None:
        """Run the pipeline via a Burr state-machine workflow."""
        from app.agent.channel.workflow import create_pipeline_app

        channel_id = str(self.channel_config.channel_id)
        app = create_pipeline_app(
            channel_id=channel_id,
            session_maker=self.session_maker,
            bot=self.bot,
            api_key=self.api_key,
            config=self.config,
            channel_config=self.channel_config,
            app_id=f"pipeline-{channel_id}",
        )

        # Run until the workflow halts at await_review or reaches done
        _action, _result, state = await app.arun(
            halt_after=["await_review", "done"],
        )

        # If halted at await_review, store state for later resumption
        post_id = state.get("post_id")
        if _action and _action.name == "await_review" and post_id:
            self._pending_reviews[post_id] = state.get_all()
            logger.info("workflow_halted_for_review", post_id=post_id, channel_id=channel_id)
        elif state.get("result_message", "").startswith("published_directly:"):
            self._posts_today += 1

    async def resume_review(self, post_id: int, decision: str) -> str:
        """Resume a halted Burr workflow after admin review.

        Parameters
        ----------
        post_id:
            The DB post ID returned when the workflow halted.
        decision:
            ``"approved"`` or ``"rejected"``.

        Returns
        -------
        A status message from the final workflow step.
        """
        from app.agent.channel.workflow import create_pipeline_app

        saved_state = self._pending_reviews.pop(post_id, None)
        if not saved_state:
            logger.warning("no_pending_review", post_id=post_id)
            return "No pending review found for this post."

        saved_state["review_decision"] = decision

        channel_id = str(self.channel_config.channel_id)
        app = create_pipeline_app(
            channel_id=channel_id,
            session_maker=self.session_maker,
            bot=self.bot,
            api_key=self.api_key,
            config=self.config,
            channel_config=self.channel_config,
            app_id=f"pipeline-{channel_id}-review-{post_id}",
            resume_state=dict(saved_state),
            entrypoint="await_review",
        )

        _action, _result, state = await app.arun(halt_after=["done"])

        result_message = state.get("result_message", "")
        if decision == "approved" and "Published" in result_message:
            self._posts_today += 1
        logger.info("workflow_review_complete", post_id=post_id, decision=decision, result=result_message)
        return result_message

    async def _run_cycle_legacy(self) -> None:
        """Legacy inline pipeline (fallback if Burr is unavailable)."""
        channel_id = str(self.channel_config.channel_id)

        # 1. Gather content from all sources
        all_items = []

        # 1a. Fetch from DB-registered RSS sources
        db_sources = await get_active_sources(self.session_maker, channel_id)
        if db_sources:
            rss_urls = [s.url for s in db_sources]
            logger.info("fetching_rss_sources", count=len(rss_urls))
            fetch_result = await fetch_all_sources(rss_urls)
            all_items.extend(fetch_result.items)

            # Track source health based on actual HTTP success/failure
            for url in fetch_result.successful_urls:
                await record_fetch_success(self.session_maker, url)
            for url in fetch_result.errored_urls:
                await record_fetch_error(self.session_maker, url, "fetch_error")

        # 1b. Discover fresh content via Perplexity Sonar
        if self.config.discovery_enabled:
            query = self.channel_config.discovery_query or self.config.discovery_query
            logger.info("discovering_content", query=query[:60])
            discovered = await discover_content(
                api_key=self.api_key,
                query=query,
                model=self.config.discovery_model,
            )
            all_items.extend(discovered)

        # Deduplicate: in-memory cache as fast first pass, then DB as source of truth
        candidates = [i for i in all_items if i.external_id not in self._seen_ids]
        if candidates:
            # Check DB for already-processed external_ids
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

        # Update in-memory cache
        for item in new_items:
            self._seen_ids[item.external_id] = None
        # Evict oldest entries if over 10k
        while len(self._seen_ids) > 10000:
            self._seen_ids.pop(next(iter(self._seen_ids)))

        if not new_items:
            logger.info("no_new_content")
            return

        logger.info("new_items_found", count=len(new_items))

        # 2. Screen for relevance
        relevant = await screen_items(
            new_items,
            api_key=self.api_key,
            model=self.config.screening_model,
            threshold=5,
        )

        if not relevant:
            logger.info("no_relevant_items")
            return

        logger.info("relevant_items", count=len(relevant))

        # 3. Fetch admin feedback context (non-blocking)
        feedback_context: str | None = None
        try:
            feedback_context = await get_feedback_summary(
                session_maker=self.session_maker,
                channel_id=channel_id,
                api_key=self.api_key,
                model=self.config.screening_model,
            )
            if feedback_context:
                logger.info("feedback_context_loaded", length=len(feedback_context))
        except Exception:
            logger.exception("feedback_context_error")

        # 4. Generate post
        language = self._language_name()
        post = await generate_post(
            relevant[:3],
            api_key=self.api_key,
            model=self.config.generation_model,
            language=language,
            feedback_context=feedback_context,
        )

        if not post:
            logger.warning("post_generation_failed")
            return

        # 5. Send for review (or direct publish if no review channel)
        review_chat_id = self.channel_config.review_chat_id or self.config.review_chat_id
        if review_chat_id:
            post_id = await send_for_review(
                bot=self.bot,
                review_chat_id=review_chat_id,
                channel_id=channel_id,
                post=post,
                source_items=relevant[:3],
                session_maker=self.session_maker,
            )
            if post_id:
                logger.info("draft_sent_for_review", post_id=post_id)
        else:
            # Fallback: direct publish (legacy behavior)
            from app.agent.channel.publisher import publish_post

            msg_id = await publish_post(self.bot, self.channel_config.channel_id, post)
            if msg_id:
                self._posts_today += 1

    async def run_once(self) -> None:
        """Run a single cycle manually (for testing or command trigger)."""
        await self._run_cycle()

    def _maybe_reset_daily_counter(self) -> None:
        """Reset daily post counter if a new day started."""
        now = datetime.now(UTC)
        if now.date() > self._last_reset.date():
            self._posts_today = 0
            self._last_reset = now

    def _language_name(self) -> str:
        """Convert language code to name."""
        lang = self.channel_config.language
        return {"ru": "Russian", "cs": "Czech", "en": "English"}.get(lang, "Russian")


class ChannelOrchestrator:
    """Manages multiple ``SingleChannelOrchestrator`` instances — one per configured channel."""

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
        self._orchestrators: list[SingleChannelOrchestrator] = []

        for ch in config.get_channels():
            self._orchestrators.append(
                SingleChannelOrchestrator(
                    bot=bot,
                    config=config,
                    channel_config=ch,
                    api_key=api_key,
                    session_maker=session_maker,
                )
            )

    @property
    def orchestrators(self) -> list[SingleChannelOrchestrator]:
        """Expose sub-orchestrators (useful for inspection/testing)."""
        return list(self._orchestrators)

    def start(self) -> None:
        """Start all sub-orchestrators."""
        if not self.config.enabled:
            logger.info("channel_agent_disabled")
            return
        if not self._orchestrators:
            logger.warning("channel_agent_no_channels_configured")
            return
        for orch in self._orchestrators:
            orch.start()
        logger.info("channel_orchestrator_started", channels=len(self._orchestrators))

    async def stop(self) -> None:
        """Stop all sub-orchestrators."""
        for orch in self._orchestrators:
            await orch.stop()
        logger.info("channel_orchestrator_stopped")

    async def run_once(self, channel_id: int | str | None = None) -> None:
        """Run a single cycle for a specific channel, or all channels if *channel_id* is ``None``."""
        targets = self._orchestrators
        if channel_id is not None:
            targets = [o for o in self._orchestrators if str(o.channel_id) == str(channel_id)]
            if not targets:
                logger.warning("run_once_channel_not_found", channel_id=channel_id)
                return
        for orch in targets:
            await orch.run_once()
