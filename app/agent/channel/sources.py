"""Content source fetchers — RSS, web pages."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import feedparser
import httpx

from app.core.logging import get_logger

logger = get_logger("channel.sources")


@dataclass
class ContentItem:
    """A discovered content item from a source."""

    source_url: str
    external_id: str
    title: str
    body: str
    url: str | None = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def summary(self) -> str:
        """Short summary for screening."""
        text = f"{self.title}\n{self.body[:500]}" if self.body else self.title
        return text.strip()


async def fetch_rss(feed_url: str, max_items: int = 10) -> list[ContentItem]:
    """Fetch items from an RSS feed."""
    items: list[ContentItem] = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:max_items]:
            ext_id = entry.get("id") or entry.get("link") or hashlib.sha256(entry.get("title", "").encode()).hexdigest()
            items.append(
                ContentItem(
                    source_url=feed_url,
                    external_id=str(ext_id),
                    title=entry.get("title", ""),
                    body=entry.get("summary", entry.get("description", "")),
                    url=entry.get("link"),
                )
            )
        logger.info("rss_fetched", feed_url=feed_url, items_count=len(items))
    except Exception:
        logger.exception("rss_fetch_error", feed_url=feed_url)
    return items


async def fetch_all_sources(rss_urls: list[str]) -> list[ContentItem]:
    """Fetch content from all configured sources."""
    all_items: list[ContentItem] = []
    for url in rss_urls:
        items = await fetch_rss(url)
        all_items.extend(items)
    return all_items
