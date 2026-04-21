"""FastAPI dependencies — DB session yielded from the shared async engine."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import Request

from app.db.session import create_session_maker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.telethon.telethon_client import TelethonClient
    from app.webapi.services.telethon_stats import TelethonStatsService


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = create_session_maker()
    async with session_maker() as session:
        yield session


async def require_super_admin(request: Request = None) -> int:  # type: ignore[assignment]  # ty: ignore[invalid-parameter-default]
    """Validate the session cookie; return the authenticated super-admin's user_id.

    Cookie name is ``settings.webapi.session_cookie_name``. Reading via
    ``request.cookies.get(name)`` keeps the name config-driven (FastAPI's
    ``Cookie(alias=...)`` would bake it into the signature at import time).
    """
    from fastapi import HTTPException

    from app.core.config import settings
    from app.webapi.auth import session_store

    if not settings.admin.super_admins:
        raise HTTPException(status_code=503, detail="No super_admin configured")

    if settings.webapi.dev_bypass_auth:
        return settings.admin.super_admins[0]

    token = request.cookies.get(settings.webapi.session_cookie_name) if request is not None else None
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    # Fresh DB session — depending on `get_session` at this layer would create
    # a circular import, and this path is lightweight.
    from app.db.session import create_session_maker

    async with create_session_maker()() as db:
        row = await session_store.load_valid_session(db, token)
        if row is None or row.user_id not in settings.admin.super_admins:
            raise HTTPException(status_code=401, detail="invalid session")
        return row.user_id


async def get_telethon() -> TelethonClient | None:
    """Return the process-wide TelethonClient if the main bot has wired one.

    Returns None when running webapi without the bot (tests, standalone
    dev), so callers must handle the no-telethon case gracefully.
    """
    from app.core.container import container

    return container.get_telethon_client()


async def get_telethon_stats(request: Request) -> TelethonStatsService:
    """Return the process-wide TelethonStatsService singleton from app.state.

    Constructed once in _lifespan (or as a no-op default in create_app for
    tests) so the TTLCache persists across requests.
    """
    return request.app.state.telethon_stats
