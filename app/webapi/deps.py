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


async def require_super_admin() -> int:
    """FastAPI dependency that returns the authenticated admin's user_id.

    Phase 0 stub: returns the first configured super_admin. No real session
    validation — access is gated by firewall in dev. Phase 4 replaces the
    body with session-cookie verification (see Phase 4 plan).
    """
    from fastapi import HTTPException

    from app.core.config import settings

    if not settings.admin.super_admins:
        raise HTTPException(
            status_code=503,
            detail="No super_admin configured — set ADMIN_SUPER_ADMINS in .env",
        )
    return settings.admin.super_admins[0]


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
