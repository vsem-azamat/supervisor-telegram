"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.webapi.routes import health, posts


def create_app() -> FastAPI:
    app = FastAPI(
        title="Moderator Bot Admin API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
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

    return app


app = create_app()
