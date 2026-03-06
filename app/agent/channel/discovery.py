"""Content discovery — uses Perplexity Sonar via OpenRouter for web search."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.agent.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.discovery")

DISCOVERY_SYSTEM = """\
You are a content researcher for a Telegram channel targeting CIS students in Czech Republic.

Find the most interesting and relevant recent news. Topics of interest:
- Czech Republic news relevant to international students
- University and education updates, visa/immigration changes
- Student housing, cost of living, job opportunities
- Technology, startups, scholarships in Czech Republic
- Cultural events and student life in Prague

Return exactly a JSON array of objects with fields: "title", "summary", "url".
Example: [{"title": "...", "summary": "...", "url": "https://..."}]
Return ONLY the JSON array, no other text. 3-5 items max.
Focus on RECENT news from the last few days."""


async def discover_content(
    api_key: str,
    query: str,
    model: str,
    *,
    http_timeout: int = 30,
    temperature: float = 0.3,
) -> list[ContentItem]:
    """Discover fresh content using Perplexity Sonar via OpenRouter.

    Uses raw HTTP to avoid PydanticAI's tool-use requirement (Sonar doesn't support tools).
    """
    from datetime import UTC, datetime
    from hashlib import sha256

    from app.agent.channel.sources import ContentItem

    try:
        content = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": DISCOVERY_SYSTEM},
                {"role": "user", "content": query},
            ],
            operation="discovery",
            temperature=temperature,
            timeout=http_timeout,
        )
        if not content:
            return []

        raw_items = json.loads(content)

        items: list[ContentItem] = []
        for raw in raw_items:
            title = raw.get("title", "")
            summary = raw.get("summary", "")
            url = raw.get("url")

            if not title:
                continue

            ext_id = sha256(f"{title}{url or ''}".encode()).hexdigest()[:16]
            items.append(
                ContentItem(
                    source_url=f"perplexity:{model}",
                    external_id=ext_id,
                    title=title,
                    body=summary,
                    url=url,
                    discovered_at=datetime.now(UTC),
                )
            )

        logger.info("discovery_complete", items_found=len(items), query=query[:60])
        return items

    except Exception:
        logger.exception("discovery_error", query=query[:60])
        return []
