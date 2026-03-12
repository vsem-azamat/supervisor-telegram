"""Shared HTTP client factory for the channel agent.

Provides a singleton httpx.AsyncClient with connection pooling, avoiding
the overhead of creating a new client per request. All channel agent modules
should use get_http_client() instead of creating their own httpx.AsyncClient.

Also provides transport-level SSRF protection via ``is_safe_url`` and
``safe_fetch`` so that every outbound request to user-controlled URLs is
validated in one place.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

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
            follow_redirects=False,
        )
    return _client


async def close_http_client() -> None:
    """Close the shared httpx client. Call during shutdown."""
    global _client  # noqa: PLW0603
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
        logger.debug("http_client_closed")


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------


def _is_ip_safe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if *ip* is a public, routable address."""
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


async def is_safe_url(url: str) -> bool:
    """Check that *url* is safe to fetch — reject internal/private IPs.

    Uses async DNS resolution to avoid blocking the event loop.
    Rejects ``file://``, ``ftp://``, and any scheme other than http/https.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        if not infos:
            return False

        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not _is_ip_safe(ip):
                return False
        return True
    except (ValueError, socket.gaierror, OSError):
        return False


class SSRFError(Exception):
    """Raised when a URL targets a private/reserved IP address."""


async def safe_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> httpx.Response:
    """Fetch *url* with SSRF validation, returning the response.

    Raises :class:`SSRFError` if the URL resolves to a private IP.
    Other HTTP errors propagate as ``httpx`` exceptions.
    """
    if not await is_safe_url(url):
        logger.warning("ssrf_blocked", url=url[:120])
        raise SSRFError(f"URL blocked by SSRF check: {url[:120]}")

    client = get_http_client(timeout=timeout)
    resp = await client.request(
        method,
        url,
        headers=headers,
        timeout=httpx.Timeout(timeout),
        follow_redirects=False,
    )
    resp.raise_for_status()
    return resp
