"""Content source fetchers — RSS, web pages."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial

import feedparser
import httpx

from app.core.logging import get_logger

logger = get_logger("channel.sources")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


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


def _strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    return _HTML_TAG_RE.sub("", text)


async def fetch_rss(feed_url: str, max_items: int = 10) -> list[ContentItem]:
    """Fetch items from an RSS feed."""
    items: list[ContentItem] = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()

        # Run blocking feedparser in executor to avoid stalling the event loop
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, partial(feedparser.parse, resp.text))
        for entry in feed.entries[:max_items]:
            ext_id = entry.get("id") or entry.get("link") or hashlib.sha256(entry.get("title", "").encode()).hexdigest()
            body = entry.get("summary", entry.get("description", ""))
            items.append(
                ContentItem(
                    source_url=feed_url,
                    external_id=str(ext_id),
                    title=entry.get("title", ""),
                    body=_strip_html(body),
                    url=entry.get("link"),
                )
            )
        logger.info("rss_fetched", feed_url=feed_url, items_count=len(items))
    except Exception:
        logger.exception("rss_fetch_error", feed_url=feed_url)
    return items


async def fetch_all_sources(rss_urls: list[str], max_concurrent: int = 5) -> list[ContentItem]:
    """Fetch content from all sources concurrently."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _fetch(url: str) -> list[ContentItem]:
        async with sem:
            return await fetch_rss(url)

    results = await asyncio.gather(*[_fetch(url) for url in rss_urls], return_exceptions=True)
    all_items: list[ContentItem] = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)
        # Exceptions already logged inside fetch_rss
    return all_items
