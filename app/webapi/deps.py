"""FastAPI dependencies — DB session yielded from the shared async engine."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from aiogram import Bot
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = get_session_maker()
    async with session_maker() as session:
        yield session


async def require_super_admin(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> int:
    """Validate the session cookie; return the authenticated super-admin's user_id.

    Cookie name is ``settings.webapi.session_cookie_name``. Reading via
    ``request.cookies.get(name)`` keeps the name config-driven (FastAPI's
    ``Cookie(alias=...)`` would bake it into the signature at import time).
    FastAPI injects a real Request at runtime. Public read-only endpoints
    live under ``/api/public`` and do not use this dependency.
    """
    from app.core.config import settings
    from app.webapi.auth import session_store

    if not settings.admin.super_admins:
        raise HTTPException(status_code=503, detail="No super_admin configured")

    token = request.cookies.get(settings.webapi.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    row = await session_store.load_valid_session(session, token)
    if row is None or row.user_id not in settings.admin.super_admins:
        raise HTTPException(status_code=401, detail="invalid session")
    return row.user_id


async def get_publish_bot(request: Request) -> Bot:
    """Return the process-wide publish Bot from app.state.

    Raises 503 if unavailable (e.g. test env that didn't override).
    """
    bot: Bot | None = getattr(request.app.state, "publish_bot", None)
    if bot is None:
        raise HTTPException(status_code=503, detail="publish bot unavailable")
    return bot
