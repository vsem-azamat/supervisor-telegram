"""Content source fetchers — RSS, web pages."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

import feedparser
import httpx

from app.agent.channel.http import get_http_client
from app.core.logging import get_logger
from app.core.time import utc_now

if TYPE_CHECKING:
    from datetime import datetime

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
    image_url: str | None = None
    discovered_at: datetime = field(default_factory=utc_now)

    @property
    def summary(self) -> str:
        """Short summary for screening."""
        text = f"{self.title}\n{self.body[:500]}" if self.body else self.title
        return text.strip()


def _strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    return _HTML_TAG_RE.sub("", text)


def _parse_feed_entries(feed: object, source_url: str, max_items: int = 10) -> list[ContentItem]:
    """Parse feedparser entries into ContentItem list."""
    from app.agent.channel.images import extract_rss_media_url

    items: list[ContentItem] = []
    for entry in feed.entries[:max_items]:  # type: ignore[attr-defined]
        ext_id = entry.get("id") or entry.get("link") or hashlib.sha256(entry.get("title", "").encode()).hexdigest()
        body = entry.get("summary", entry.get("description", ""))
        items.append(
            ContentItem(
                source_url=source_url,
                external_id=str(ext_id),
                title=entry.get("title", ""),
                body=_strip_html(body),
                url=entry.get("link"),
                image_url=extract_rss_media_url(entry),
            )
        )
    return items


async def fetch_rss(feed_url: str, max_items: int = 10, *, http_timeout: int = 30) -> list[ContentItem]:
    """Fetch items from an RSS feed."""
    try:
        client = get_http_client(timeout=http_timeout)
        resp = await client.get(feed_url, timeout=httpx.Timeout(http_timeout))
        resp.raise_for_status()

        # Run blocking feedparser in executor to avoid stalling the event loop
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, partial(feedparser.parse, resp.text))
        items = _parse_feed_entries(feed, feed_url, max_items=max_items)
        logger.info("rss_fetched", feed_url=feed_url, items_count=len(items))
        return items
    except Exception:
        logger.exception("rss_fetch_error", feed_url=feed_url)
        return []


@dataclass
class FetchResult:
    """Result of fetching content from all sources, with per-URL status."""

    items: list[ContentItem]
    errored_urls: set[str]  # URLs that failed during HTTP fetch
    successful_urls: set[str]  # URLs that were fetched successfully (may have 0 items)


async def fetch_all_sources(rss_urls: list[str], max_concurrent: int = 5, *, http_timeout: int = 30) -> FetchResult:
    """Fetch content from all sources concurrently.

    Returns a :class:`FetchResult` containing items and per-URL success/error info.
    """
    sem = asyncio.Semaphore(max_concurrent)
    errored_urls: set[str] = set()
    successful_urls: set[str] = set()

    async def _fetch(url: str) -> list[ContentItem]:
        async with sem:
            try:
                client = get_http_client(timeout=http_timeout)
                resp = await client.get(url, timeout=httpx.Timeout(http_timeout))
                resp.raise_for_status()

                loop = asyncio.get_running_loop()
                feed = await loop.run_in_executor(None, partial(feedparser.parse, resp.text))
                items = _parse_feed_entries(feed, url)
                logger.info("rss_fetched", feed_url=url, items_count=len(items))
                successful_urls.add(url)
                return items
            except Exception:
                logger.exception("rss_fetch_error", feed_url=url)
                errored_urls.add(url)
                return []

    results = await asyncio.gather(*[_fetch(url) for url in rss_urls], return_exceptions=True)
    all_items: list[ContentItem] = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)
    return FetchResult(items=all_items, errored_urls=errored_urls, successful_urls=successful_urls)
