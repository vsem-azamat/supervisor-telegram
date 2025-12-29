"""Helper to fetch current tunnel URL dynamically in development.

Supports both Cloudflare Tunnel (cloudflared) and ngrok.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


async def get_current_tunnel_url() -> str | None:
    """
    Fetch current tunnel public URL from cloudflared metrics or ngrok API.

    Returns:
        Current HTTPS URL or None if not available
    """
    # Try cloudflared first (preferred)
    url = await _get_cloudflared_url()
    if url:
        return url

    # Fallback to ngrok
    return await _get_ngrok_url()


async def _get_cloudflared_url() -> str | None:
    """Read URL from shared volume written by tunnel-url-extractor sidecar."""
    try:
        from pathlib import Path

        with Path("/tunnel/url.txt").open() as f:
            url = f.read().strip()
            if url and url.startswith("https://") and "trycloudflare.com" in url:
                logger.info(f"Fetched cloudflared tunnel URL: {url}")
                return url

        logger.debug("Invalid or empty URL in /tunnel/url.txt")
        return None

    except FileNotFoundError:
        logger.debug("Tunnel URL file not found at /tunnel/url.txt")
        return None
    except Exception as e:
        logger.debug(f"cloudflared not available: {e}")
        return None


async def _get_ngrok_url() -> str | None:
    """Fetch URL from ngrok API (legacy fallback)."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://ngrok:4040/api/tunnels")
            response.raise_for_status()
            data: dict[str, list[dict[str, str]]] = response.json()

            tunnels = data.get("tunnels", [])
            for tunnel in tunnels:
                public_url = tunnel.get("public_url", "")
                if isinstance(public_url, str) and public_url.startswith("https://"):
                    logger.info(f"Fetched ngrok URL: {public_url}")
                    return public_url

            logger.warning("No HTTPS tunnel found in ngrok API response")
            return None

    except Exception as e:
        logger.debug(f"ngrok not available: {e}")
        return None


# Backwards compatibility alias
get_current_ngrok_url = get_current_tunnel_url
