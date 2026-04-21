"""FastAPI app factory."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import get_logger
from app.db.session import create_session_maker
from app.webapi.routes import agent, channels, chats, costs, health, posts, spam, stats
from app.webapi.services.telethon_stats import TelethonStatsService
from app.webapi.snapshot_loop import run_snapshot_loop

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger("webapi.main")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    from app.core.container import container

    session_maker = create_session_maker()
    telethon = container.get_telethon_client()
    _app.state.telethon_stats = TelethonStatsService(telethon=telethon)
    task: asyncio.Task[None] | None = None
    if telethon is not None:
        task = asyncio.create_task(run_snapshot_loop(session_maker=session_maker, telethon=telethon))
        logger.info("snapshot_loop started")
    else:
        logger.info("snapshot_loop not started — telethon unavailable")
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            logger.info("snapshot_loop stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Moderator Bot Admin API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    # Dev-only: wide-open CORS so the frontend can hit the API from any VPS
    # hostname. When auth lands, tighten to an allowlist.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(posts.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(chats.router, prefix="/api")
    app.include_router(costs.router, prefix="/api")
    app.include_router(spam.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(agent.router, prefix="/api")

    # Default no-op singleton for test environments (ASGITransport bypasses
    # lifespan). _lifespan replaces this with the real instance at startup.
    app.state.telethon_stats = TelethonStatsService(telethon=None)

    return app


app = create_app()
