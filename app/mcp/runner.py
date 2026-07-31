"""Serve the MCP control plane from inside the bot process.

The endpoint used to be mounted on the web API, which cannot reach the two
things moderation tools depend on: the Telethon user session, whose SQLite file
only one process may open, and the bot that sends confirmation keyboards and
owns their callbacks. Running here removes both gaps.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Generator

logger = get_logger("mcp.runner")


def _build_server(app: Any) -> Any:
    """Wrap uvicorn so it leaves this process's signal handling alone.

    ``Server.serve()`` installs its own SIGINT/SIGTERM handlers through
    ``capture_signals()``. Here that would replace the ones aiogram's polling
    installed and leave the bot without a shutdown path, so the hook is
    neutralised rather than the signals shared.
    """
    import uvicorn

    class _BotOwnsSignals(uvicorn.Server):
        @contextlib.contextmanager
        def capture_signals(self) -> Generator[None, None, None]:
            yield

    config = uvicorn.Config(
        app,
        host=settings.mcp.host,
        port=settings.mcp.port,
        log_config=None,
        lifespan="on",
    )
    return _BotOwnsSignals(config)


async def run_mcp_server() -> None:
    """Run the token-protected MCP endpoint until cancelled.

    Returns immediately when MCP is inactive so the caller can add this to its
    task list unconditionally.
    """
    if not settings.mcp.active:
        logger.info("mcp_disabled")
        return

    from app.mcp.server import build_mcp_asgi_app

    server = _build_server(build_mcp_asgi_app(token=settings.mcp.token, path=settings.mcp.path))

    logger.info("mcp_serving", host=settings.mcp.host, port=settings.mcp.port, path=settings.mcp.path)
    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("mcp_cancelled")
        raise
    finally:
        logger.info("mcp_stopped")
