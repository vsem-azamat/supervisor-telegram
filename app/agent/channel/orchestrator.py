"""Channel content orchestrator — coordinates the full pipeline."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.agent.channel.generator import generate_post, screen_items
from app.agent.channel.publisher import publish_post
from app.agent.channel.sources import fetch_all_sources
from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Bot

    from app.agent.channel.config import ChannelAgentSettings
    from app.agent.channel.generator import GeneratedPost

logger = get_logger("channel.orchestrator")


class ChannelOrchestrator:
    """Orchestrates the content pipeline: fetch -> screen -> generate -> publish."""

    def __init__(self, bot: Bot, config: ChannelAgentSettings, api_key: str) -> None:
        self.bot = bot
        self.config = config
        self.api_key = api_key
        self._seen_ids: set[str] = set()
        self._posts_today: int = 0
        self._last_reset: datetime = datetime.now(UTC)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the background content loop."""
        if not self.config.enabled:
            logger.info("channel_agent_disabled")
            return
        if not self.config.channel_id:
            logger.warning("channel_agent_no_channel_id")
            return
        if not self.config.rss_source_list:
            logger.warning("channel_agent_no_sources")
            return
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "channel_agent_started",
            channel_id=self.config.channel_id,
            sources=len(self.config.rss_source_list),
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
        """Main loop: fetch, screen, generate, publish on schedule."""
        # Small initial delay to let the bot fully start
        await asyncio.sleep(5)

        while True:
            try:
                await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("channel_cycle_error")

            await asyncio.sleep(self.config.fetch_interval_minutes * 60)

    async def _run_cycle(self) -> None:
        """Run one full pipeline cycle."""
        self._maybe_reset_daily_counter()

        if self._posts_today >= self.config.max_posts_per_day:
            logger.info("daily_post_limit_reached", count=self._posts_today)
            return

        # 1. Discover
        logger.info("cycle_start", sources=len(self.config.rss_source_list))
        items = await fetch_all_sources(self.config.rss_source_list)

        # Deduplicate against already seen
        new_items = [i for i in items if i.external_id not in self._seen_ids]
        for item in new_items:
            self._seen_ids.add(item.external_id)

        if not new_items:
            logger.info("no_new_content")
            return

        logger.info("new_items_found", count=len(new_items))

        # 2. Screen
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

        # 3. Generate
        post = await generate_post(
            relevant[:3],
            api_key=self.api_key,
            model=self.config.generation_model,
            language=self._language_name(),
        )

        if not post:
            logger.warning("post_generation_failed")
            return

        # 4. Publish (or send for approval)
        if self.config.require_approval:
            await self._send_for_approval(post)
        else:
            msg_id = await publish_post(self.bot, self.config.channel_id, post)
            if msg_id:
                self._posts_today += 1

    async def _send_for_approval(self, post: GeneratedPost) -> None:
        """Send post draft to admin for approval."""
        from app.core.config import settings

        admin_id = settings.admin.super_admins[0]
        preview_text = (
            f"<b>New post draft for channel {self.config.channel_id}:</b>\n\n"
            f"{post.text}\n\n"
            "---\n"
            "Reply /approve to publish or /reject to discard."
        )
        try:
            await self.bot.send_message(admin_id, preview_text, parse_mode="HTML")
            logger.info("approval_sent", admin_id=admin_id)
        except Exception:
            logger.exception("approval_send_error", admin_id=admin_id)

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
