"""Split multi-topic content items into individual topics and enrich with web search.

Perplexity Sonar often returns synthesized summaries that mix multiple news stories.
This module splits them into individual ContentItems, each about one topic, and
optionally enriches sparse items with additional details via Brave Search.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING

from pydantic import BaseModel, TypeAdapter

from app.agent.channel.llm_client import openrouter_chat_completion
from app.core.logging import get_logger
from app.core.time import utc_now

if TYPE_CHECKING:
    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.topic_splitter")


# ---------------------------------------------------------------------------
# Pydantic models for LLM responses
# ---------------------------------------------------------------------------


class SplitTopic(BaseModel):
    """A single news topic extracted by the split LLM."""

    title: str
    summary: str = ""
    url: str | None = None


class EnrichedTopic(BaseModel):
    """A topic enriched with a source URL from web search."""

    title: str
    summary: str = ""
    url: str | None = None


class ContentSource(StrEnum):
    """Discriminator for how a ContentItem was produced."""

    RSS = "rss"
    PERPLEXITY = "perplexity"
    BRAVE = "brave"
    SPLIT = "split"
    ENRICHED = "enriched"
    ASSISTANT = "assistant"


_split_topics_adapter: TypeAdapter[list[SplitTopic]] = TypeAdapter(list[SplitTopic])
_enriched_topic_adapter: TypeAdapter[EnrichedTopic] = TypeAdapter(EnrichedTopic)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SPLIT_PROMPT = """\
You are a news editor. Analyze the content items below and split them into \
individual, self-contained news topics.

Rules:
- Each output item must be about ONE specific news story or event.
- If an input item is already about a single topic, keep it as-is.
- If an input item mixes multiple topics (common with AI-synthesized content), \
split it into separate items.
- Preserve the source URL for each topic. If the original item had one URL but \
multiple topics, assign the URL to the most relevant topic and leave others \
with url=null.
- Keep titles concise and factual.
- Keep summaries informative (2-3 sentences).

Return a JSON array of objects: {{"title": "...", "summary": "...", "url": "..." or null}}
Return ONLY the JSON array."""

ENRICH_PROMPT = """\
You have a news topic that lacks a source URL or detailed information. \
Using the web search results below, find the best matching source and \
enrich the summary with concrete facts.

Topic: {title}
Current summary: {summary}

Search results:
{search_results}

Return a JSON object: {{"title": "...", "summary": "...", "url": "..."}}
If no search result matches, return the original with url=null.
Return ONLY the JSON object."""

_SYNTH_PREFIXES = ("perplexity:", "sonar:", "split:")


def _is_synthesized(item: ContentItem) -> bool:
    """Check if an item came from a synthesis source (not a direct RSS/URL)."""
    return item.source_url.startswith(_SYNTH_PREFIXES)


def _topic_to_content_item(
    topic: SplitTopic | EnrichedTopic,
    source_label: str,
) -> ContentItem:
    """Convert a Pydantic topic model to a ContentItem."""
    from app.agent.channel.sources import ContentItem as ContentItemClass

    ext_id = sha256(f"{source_label}:{topic.title}{topic.url or ''}".encode()).hexdigest()[:16]
    return ContentItemClass(
        source_url=source_label,
        external_id=ext_id,
        title=topic.title,
        body=topic.summary,
        url=topic.url,
        discovered_at=utc_now(),
    )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


async def split_topics(
    items: list[ContentItem],
    api_key: str,
    model: str,
    *,
    temperature: float = 0.1,
    timeout: int = 30,
) -> list[ContentItem]:
    """Split multi-topic ContentItems into individual single-topic items.

    Items from RSS (which are already single-topic) pass through unchanged.
    Only items from synthesis sources (Perplexity, etc.) are processed.
    """
    if not items:
        return []

    rss_items = [item for item in items if not _is_synthesized(item)]
    synth_items = [item for item in items if _is_synthesized(item)]

    if not synth_items:
        return items

    content_parts = []
    for i, item in enumerate(synth_items):
        content_parts.append(f"[{i}] Title: {item.title}\n    URL: {item.url or 'N/A'}\n    Summary: {item.body[:500]}")
    content_text = "\n\n".join(content_parts)

    try:
        response = await openrouter_chat_completion(
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": SPLIT_PROMPT},
                {"role": "user", "content": content_text},
            ],
            operation="topic_split",
            temperature=temperature,
            timeout=timeout,
        )
        if not response:
            logger.warning("topic_split_empty_response")
            return items

        topics = _split_topics_adapter.validate_json(response)
        source_label = f"{ContentSource.SPLIT}:{model}"
        split_items = [_topic_to_content_item(t, source_label) for t in topics if t.title]

        logger.info(
            "topic_split_done",
            input_synth=len(synth_items),
            output_topics=len(split_items),
        )
        return rss_items + split_items

    except Exception:
        logger.exception("topic_split_error")
        return items


async def enrich_items(
    items: list[ContentItem],
    api_key: str,
    model: str,
    brave_api_key: str,
    *,
    temperature: float = 0.2,
    timeout: int = 30,
) -> list[ContentItem]:
    """Enrich ContentItems that lack a URL by searching Brave and asking LLM to match.

    Items that already have a URL are returned unchanged.
    """
    if not items or not brave_api_key:
        return items

    from app.agent.channel.brave_search import brave_web_search

    enriched: list[ContentItem] = []

    for item in items:
        if item.url:
            enriched.append(item)
            continue

        try:
            search_results = await brave_web_search(brave_api_key, item.title, count=3, freshness="pw", timeout=15)
            if not search_results:
                enriched.append(item)
                continue

            results_text = "\n".join(f"- {r['title']}: {r['url']}\n  {r['description'][:200]}" for r in search_results)

            response = await openrouter_chat_completion(
                api_key=api_key,
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": ENRICH_PROMPT.format(
                            title=item.title,
                            summary=item.body[:300],
                            search_results=results_text,
                        ),
                    },
                ],
                operation="topic_enrich",
                temperature=temperature,
                timeout=timeout,
            )
            if not response:
                enriched.append(item)
                continue

            topic = _enriched_topic_adapter.validate_json(response)
            source_label = f"{ContentSource.ENRICHED}:{model}"
            enriched_item = _topic_to_content_item(topic, source_label)
            # Preserve original discovered_at
            enriched_item.discovered_at = item.discovered_at
            enriched.append(enriched_item)
            logger.info("topic_enriched", title=topic.title[:60], url=topic.url)

        except Exception:
            logger.exception("topic_enrich_error", title=item.title[:60])
            enriched.append(item)

    return enriched


async def split_and_enrich(
    items: list[ContentItem],
    api_key: str,
    model: str,
    brave_api_key: str = "",
    *,
    temperature: float = 0.2,
    timeout: int = 30,
) -> list[ContentItem]:
    """Full pipeline: split multi-topic items, then enrich URL-less items via Brave."""
    split = await split_topics(items, api_key, model, temperature=temperature, timeout=timeout)
    if brave_api_key:
        split = await enrich_items(split, api_key, model, brave_api_key, temperature=temperature, timeout=timeout)
    return split
