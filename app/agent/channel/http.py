"""Shared HTTP client factory for the channel agent.

Provides a singleton httpx.AsyncClient with connection pooling, avoiding
the overhead of creating a new client per request. All channel agent modules
should use get_http_client() instead of creating their own httpx.AsyncClient.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

logger = get_logger("channel.http")

_client: httpx.AsyncClient | None = None

# Connection pool limits — shared across all channel agent modules
_POOL_LIMITS = httpx.Limits(max_connections=30, max_keepalive_connections=10)


def get_http_client(*, timeout: int = 30) -> httpx.AsyncClient:
    """Return the shared httpx client, creating one if needed.

    The timeout parameter is only used on first creation.
    Use per-request ``timeout=httpx.Timeout(N)`` for custom timeouts.
    """
    global _client  # noqa: PLW0603
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=timeout,
            limits=_POOL_LIMITS,
            follow_redirects=True,
        )
    return _client


async def close_http_client() -> None:
    """Close the shared httpx client. Call during shutdown."""
    global _client  # noqa: PLW0603
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
        logger.debug("http_client_closed")
