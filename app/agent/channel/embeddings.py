"""Embedding client for semantic deduplication via OpenRouter.

Uses the shared LLM client from llm_client.py to avoid HTTP client proliferation.
The embedding dimension (768) is a schema constant — changing it requires a DB migration.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("channel.embeddings")

# Schema constants — changing these requires a DB migration + re-embedding
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMS = 768


async def get_embeddings(
    texts: list[str],
    *,
    api_key: str,
    model: str = EMBEDDING_MODEL,
    timeout: int = 15,
) -> list[list[float]]:
    """Get embeddings for a list of texts via OpenRouter.

    Returns a list of float vectors (768-dim), one per input text.
    Raises on API error.
    """
    if not texts:
        return []

    import httpx

    from app.agent.channel.http import get_http_client

    base_url = settings.agent.openrouter_base_url

    payload: dict[str, object] = {
        "model": model,
        "input": texts,
        "dimensions": EMBEDDING_DIMS,
    }

    client = get_http_client(timeout=timeout)
    resp = await client.post(
        f"{base_url}/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=httpx.Timeout(timeout),
    )
    resp.raise_for_status()
    data = resp.json()

    # Sort by index to ensure order matches input
    sorted_data = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in sorted_data]
