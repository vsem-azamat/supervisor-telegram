"""Standalone runner for the webapp stats API (aiohttp).

Can be started independently or integrated into the bot process.
"""

from __future__ import annotations

from aiohttp import web

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.db.session import create_session_maker
from app.presentation.api.routes import create_api_app

logger = get_logger("api")


def run_api() -> None:
    """Run the API server as a standalone process."""
    if not settings.webapp.api_enabled:
        logger.warning("API is disabled. Set WEBAPP_API_ENABLED=true to enable.")
        return

    session_maker = create_session_maker()
    app = create_api_app(
        session_maker=session_maker,
        allowed_emails=settings.webapp.allowed_emails,
        allowed_origins=[settings.webapp.url] if settings.webapp.url else [],
    )
    logger.info("Starting API server", port=settings.webapp.api_port)
    web.run_app(app, port=settings.webapp.api_port, print=None)


if __name__ == "__main__":
    run_api()
