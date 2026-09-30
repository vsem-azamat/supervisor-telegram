"""Liveness, and the database, which fails independently of it.

Its own router with no prefix: `/healthz` is not part of the versioned API and
must not move when the API version does.

Nothing about Telegram. This process holds no webhook: the token is the
moderator bot's and so are its updates. See docs/architecture.md.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from students_cz.api.deps import SessionDep

_STARTED_AT = datetime.now(UTC)

health_router = APIRouter(tags=["ops"])


@health_router.get("/healthz")
async def healthz(session: SessionDep) -> dict[str, str | int]:
    """Liveness plus the database."""
    await session.execute(select(1))
    uptime = datetime.now(UTC) - _STARTED_AT
    return {
        "status": "ok",
        "database": "ok",
        "uptime_seconds": int(uptime / timedelta(seconds=1)),
    }
