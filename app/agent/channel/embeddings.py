"""Embedding client for semantic deduplication via OpenRouter.

Uses the shared LLM client from llm_client.py to avoid HTTP client proliferation.
The embedding dimension (768) is a schema constant — changing it requires a DB migration.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.agent.channel.http import get_http_client
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("channel.embeddings")

# Schema constants — changing these requires a DB migration + re-embedding
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMS = 768


def _is_transient(exc: BaseException) -> bool:
    """Retry on timeouts and transient HTTP errors (including OpenRouter's spurious 401s)."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (401, 429, 502, 503, 504)
    return False


_EMBEDDING_RETRY = retry(
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


async def get_embeddings(
    texts: list[str],
    *,
    api_key: str,
    model: str = EMBEDDING_MODEL,
    timeout: int = 15,
) -> list[list[float]]:
    """Get embeddings for a list of texts via OpenRouter.

    Returns a list of float vectors (768-dim), one per input text.
    Raises on API error after 3 retries.
    """
    if not texts:
        return []

    base_url = settings.agent.openrouter_base_url

    payload: dict[str, object] = {
        "model": model,
        "input": texts,
        "dimensions": EMBEDDING_DIMS,
    }

    @_EMBEDDING_RETRY
    async def _call() -> dict[str, object]:
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
        return resp.json()

    data = await _call()

    # Sort by index to ensure order matches input
    sorted_data = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in sorted_data]
