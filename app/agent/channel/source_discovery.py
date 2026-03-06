"""Source discovery agent — finds new RSS feeds via Perplexity Sonar."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx

from app.agent.channel.cost_tracker import extract_usage_from_openrouter_response, log_usage
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
    model: str = "perplexity/sonar",
) -> list[dict[str, str]]:
    """Use Perplexity Sonar to find RSS feed URLs for a given topic."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": FIND_FEEDS_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()

        data = resp.json()
        usage = extract_usage_from_openrouter_response(data, model, "source_discovery")
        if usage:
            await log_usage(usage)
        content = data["choices"][0]["message"]["content"].strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        feeds = json.loads(content)
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
    model: str = "perplexity/sonar",
) -> int:
    """Discover RSS feeds, validate them, and add working ones to DB.

    Returns the number of new sources added.
    """
    feeds = await discover_rss_feeds(api_key, query, model)
    added = 0

    for feed in feeds:
        url = feed.get("url", "")
        title = feed.get("title")
        if not url:
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
