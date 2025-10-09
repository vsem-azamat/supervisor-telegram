"""Helper to fetch current ngrok URL dynamically in development."""

import logging

import httpx

logger = logging.getLogger(__name__)


async def get_current_ngrok_url() -> str | None:
    """
    Fetch current ngrok public URL from ngrok API.

    Returns:
        Current ngrok HTTPS URL or None if not available
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://ngrok:4040/api/tunnels")
            response.raise_for_status()
            data: dict[str, list[dict[str, str]]] = response.json()

            # Find HTTPS tunnel
            tunnels = data.get("tunnels", [])
            for tunnel in tunnels:
                public_url = tunnel.get("public_url", "")
                if isinstance(public_url, str) and public_url.startswith("https://"):
                    logger.info(f"Fetched current ngrok URL: {public_url}")
                    return public_url

            logger.warning("No HTTPS tunnel found in ngrok API response")
            return None

    except Exception as e:
        logger.warning(f"Failed to fetch ngrok URL: {e}")
        return None
