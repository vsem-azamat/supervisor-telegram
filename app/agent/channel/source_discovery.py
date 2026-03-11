"""Source discovery agent — finds new RSS feeds via Perplexity Sonar."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.agent.channel.llm_client import openrouter_chat_completion
from app.agent.channel.source_manager import add_source
from app.agent.channel.sources import fetch_rss
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger("channel.source_discovery")

FIND_FEEDS_PROMPT = """\
You are a research assistant. Find RSS/Atom feed URLs for the given topic.

Requirements:
- Return ONLY a JSON array of objects with "url" and "title" fields
- Each URL must be a direct RSS/Atom feed URL (ending in /feed/, /rss, .xml, etc.)
- Include 5-10 feeds
- Focus on active, regularly updated feeds
- Prefer English and Czech language sources
- No duplicates

Example: [{"url": "https://example.com/feed/", "title": "Example Blog"}]
Return ONLY the JSON array."""


async def discover_rss_feeds(
    api_key: str,
    query: str,
    model: str,
    *,
    http_timeout: int = 30,
    temperature: float = 0.2,
) -> list[dict[str, str]]:
    """Use Perplexity Sonar to find RSS feed URLs for a given topic."""
    try:
        content = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": FIND_FEEDS_PROMPT},
                {"role": "user", "content": query},
            ],
            operation="source_discovery",
            temperature=temperature,
            timeout=http_timeout,
        )
        if not content:
            return []

        feeds = json.loads(content)
        if not isinstance(feeds, list):
            logger.warning("feed_discovery_unexpected_format", type=type(feeds).__name__)
            return []
        logger.info("feeds_discovered", count=len(feeds), query=query[:60])
        return feeds

    except Exception:
        logger.exception("feed_discovery_error", query=query[:60])
        return []


async def validate_feed(url: str) -> bool:
    """Check if a URL is a valid, working RSS feed with items."""
    try:
        items = await fetch_rss(url, max_items=1)
        return len(items) > 0
    except Exception:
        return False


async def discover_and_add_sources(
    api_key: str,
    channel_id: str,
    query: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str,
    *,
    http_timeout: int = 30,
    temperature: float = 0.2,
) -> int:
    """Discover RSS feeds, validate them, and add working ones to DB.

    Returns the number of new sources added.
    """
    feeds = await discover_rss_feeds(api_key, query, model, http_timeout=http_timeout, temperature=temperature)
    added = 0

    for feed in feeds:
        url = feed.get("url", "")
        title = feed.get("title")
        if not url:
            continue

        # SSRF check: LLM-returned URLs are untrusted
        from app.agent.channel.http import is_safe_url

        if not await is_safe_url(url):
            logger.warning("discovery_ssrf_blocked", url=url)
            continue

        # Validate: actually fetch the feed and check it returns items
        if await validate_feed(url):
            if await add_source(session_maker, channel_id, url, title=title, added_by="discovery"):
                added += 1
                logger.info("source_discovered_and_added", url=url, title=title)
        else:
            logger.debug("source_invalid", url=url)

    logger.info("source_discovery_complete", discovered=len(feeds), added=added)
    return added
