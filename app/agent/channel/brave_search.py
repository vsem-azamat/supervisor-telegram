"""Brave Web Search API client for content discovery."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

import httpx

from app.agent.channel.http import get_http_client
from app.core.logging import get_logger
from app.core.time import utc_now

if TYPE_CHECKING:
    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.brave_search")

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
VALID_FRESHNESS = {"pd", "pw", "pm", "py"}


async def brave_web_search(
    api_key: str,
    query: str,
    *,
    count: int = 10,
    freshness: str = "pw",
    timeout: int = 15,
) -> list[dict[str, str]]:
    """Execute a Brave Web Search and return raw results.

    Args:
        api_key: Brave Search API key.
        query: Search query string.
        count: Number of results (max 20).
        freshness: Time filter — pd (past day), pw (past week), pm (past month), py (past year).
        timeout: HTTP timeout in seconds.

    Returns:
        List of dicts with keys: title, url, description.
    """
    if not api_key:
        raise ValueError("Brave API key is required")

    if freshness not in VALID_FRESHNESS:
        freshness = "pw"

    count = max(1, min(count, 20))

    client = get_http_client(timeout=timeout)
    resp = await client.get(
        BRAVE_SEARCH_URL,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        params={
            "q": query,
            "count": count,
            "freshness": freshness,
            "text_decorations": "false",
        },
        timeout=httpx.Timeout(timeout),
    )
    resp.raise_for_status()
    data = resp.json()

    results: list[dict[str, str]] = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            }
        )

    logger.info("brave_search_done", query=query[:60], results=len(results))
    return results


async def discover_content_brave(
    api_key: str,
    query: str,
    *,
    count: int = 10,
    freshness: str = "pw",
    timeout: int = 15,
) -> list[ContentItem]:
    """Discover content using Brave Web Search and return as ContentItems.

    This is a direct alternative to Perplexity Sonar discovery.
    Brave is better for: specific factual queries, recent news, URL-based results.
    Perplexity is better for: synthesized summaries, broader topic exploration.
    """
    from app.agent.channel.sources import ContentItem

    try:
        raw_results = await brave_web_search(api_key, query, count=count, freshness=freshness, timeout=timeout)

        items: list[ContentItem] = []
        for raw in raw_results:
            title = raw.get("title", "")
            url = raw.get("url", "")
            description = raw.get("description", "")

            if not title or not url:
                continue

            ext_id = sha256(f"{title}{url}".encode()).hexdigest()[:16]
            items.append(
                ContentItem(
                    source_url=url,
                    external_id=ext_id,
                    title=title,
                    body=description,
                    url=url,
                    discovered_at=utc_now(),
                )
            )

        logger.info("brave_discovery_complete", items_found=len(items), query=query[:60])
        return items

    except Exception:
        logger.exception("brave_discovery_error", query=query[:60])
        return []


async def brave_search_for_assistant(
    api_key: str,
    query: str,
    *,
    count: int = 5,
    freshness: str = "pw",
) -> str:
    """Run a Brave search and return formatted results for the assistant agent."""
    try:
        results = await brave_web_search(api_key, query, count=count, freshness=freshness)
        if not results:
            return f"No results found for: {query}"

        lines = [f"Search results for '{query}' ({len(results)} found):\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r['title']}**")
            lines.append(f"   {r['url']}")
            if r["description"]:
                lines.append(f"   {r['description'][:150]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        logger.exception("brave_search_assistant_error", query=query)
        return f"Search failed for: {query}. Error: {type(exc).__name__}: {exc}"
