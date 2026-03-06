"""Channel content orchestrator — coordinates the full pipeline."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.agent.channel.discovery import discover_content
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

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.config import ChannelAgentSettings

logger = get_logger("channel.orchestrator")


class ChannelOrchestrator:
    """Orchestrates the content pipeline: discover -> screen -> generate -> review -> publish."""

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
        self._seen_ids: set[str] = set()
        self._posts_today: int = 0
        self._last_reset: datetime = datetime.now(UTC)
        self._last_source_discovery: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the background content loop."""
        if not self.config.enabled:
            logger.info("channel_agent_disabled")
            return
        if not self.config.channel_id:
            logger.warning("channel_agent_no_channel_id")
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "channel_agent_started",
            channel_id=self.config.channel_id,
            interval_min=self.config.fetch_interval_minutes,
        )

    async def stop(self) -> None:
        """Stop the background loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("channel_agent_stopped")

    async def _run_loop(self) -> None:
        """Main loop: discover sources, fetch content, screen, generate, send for review."""
        await asyncio.sleep(5)

        # Seed DB sources from env config on first run (deprecated, for migration)
        if self.config.rss_source_list:
            await seed_sources_from_env(
                self.session_maker,
                str(self.config.channel_id),
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
                logger.exception("channel_cycle_error")

            await asyncio.sleep(self.config.fetch_interval_minutes * 60)

    async def _maybe_discover_sources(self) -> None:
        """Run source discovery if enough time has passed."""
        if not self.config.source_discovery_enabled:
            return

        now = datetime.now(UTC)
        interval = self.config.source_discovery_interval_hours * 3600

        if self._last_source_discovery and (now - self._last_source_discovery).total_seconds() < interval:
            return

        logger.info("source_discovery_start", query=self.config.source_discovery_query[:60])
        added = await discover_and_add_sources(
            api_key=self.api_key,
            channel_id=str(self.config.channel_id),
            query=self.config.source_discovery_query,
            session_maker=self.session_maker,
            model=self.config.discovery_model,
        )
        self._last_source_discovery = now
        logger.info("source_discovery_done", added=added)

    async def _run_cycle(self) -> None:
        """Run one full pipeline cycle."""
        self._maybe_reset_daily_counter()

        if self._posts_today >= self.config.max_posts_per_day:
            logger.info("daily_post_limit_reached", count=self._posts_today)
            return

        channel_id = str(self.config.channel_id)

        # 1. Gather content from all sources
        all_items = []

        # 1a. Fetch from DB-registered RSS sources
        db_sources = await get_active_sources(self.session_maker, channel_id)
        if db_sources:
            rss_urls = [s.url for s in db_sources]
            logger.info("fetching_rss_sources", count=len(rss_urls))
            rss_items = await fetch_all_sources(rss_urls)
            all_items.extend(rss_items)

            # Track source health
            fetched_urls = {item.source_url for item in rss_items}
            for url in rss_urls:
                if url in fetched_urls:
                    await record_fetch_success(self.session_maker, url)
                else:
                    await record_fetch_error(self.session_maker, url, "no_items_returned")

        # 1b. Discover fresh content via Perplexity Sonar
        if self.config.discovery_enabled:
            logger.info("discovering_content", query=self.config.discovery_query[:60])
            discovered = await discover_content(
                api_key=self.api_key,
                query=self.config.discovery_query,
                model=self.config.discovery_model,
            )
            all_items.extend(discovered)

        # Deduplicate against already seen
        new_items = [i for i in all_items if i.external_id not in self._seen_ids]
        for item in new_items:
            self._seen_ids.add(item.external_id)

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

        # 3. Generate post
        post = await generate_post(
            relevant[:3],
            api_key=self.api_key,
            model=self.config.generation_model,
            language=self._language_name(),
        )

        if not post:
            logger.warning("post_generation_failed")
            return

        # 4. Send for review (or direct publish if no review channel)
        if self.config.review_chat_id:
            post_id = await send_for_review(
                bot=self.bot,
                review_chat_id=self.config.review_chat_id,
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

            msg_id = await publish_post(self.bot, self.config.channel_id, post)
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
        return {"ru": "Russian", "cs": "Czech", "en": "English"}.get(self.config.language, "Russian")
