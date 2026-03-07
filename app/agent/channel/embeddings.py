"""Embedding client for semantic deduplication via OpenRouter."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("channel.embeddings")

# Default model — good multilingual quality at low cost ($0.02/1M tokens)
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EMBEDDING_DIMS = 768


async def get_embeddings(
    texts: list[str],
    *,
    api_key: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMS,
    timeout: int = 15,
) -> list[list[float]]:
    """Get embeddings for a list of texts via OpenRouter.

    Returns a list of float vectors, one per input text.
    Raises on API error.
    """
    if not texts:
        return []

    base_url = settings.agent.openrouter_base_url

    payload: dict[str, object] = {
        "model": model,
        "input": texts,
        "dimensions": dimensions,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    # Sort by index to ensure order matches input
    sorted_data = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in sorted_data]


async def get_embedding(
    text: str,
    *,
    api_key: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMS,
    timeout: int = 15,
) -> list[float]:
    """Get embedding for a single text."""
    results = await get_embeddings([text], api_key=api_key, model=model, dimensions=dimensions, timeout=timeout)
    return results[0]
