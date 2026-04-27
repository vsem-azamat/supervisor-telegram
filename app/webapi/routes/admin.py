"""Admin / settings — read-only system status + active session management.

Mutations beyond ``revoke`` are intentionally out of scope: most settings
(feature flags, model choices, env-driven config) live in the deployment
config and would need schema work to become DB-backed. The /settings page
is a security + observability surface, not a config editor.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AdminSession
from app.webapi.auth import session_store
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import AdminSessionRead, FeatureFlagRead, SystemStatus

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/sessions", response_model=list[AdminSessionRead])
async def list_sessions(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[AdminSessionRead]:
    """List the calling admin's active sessions, current one flagged."""
    rows = (
        (
            await session.execute(
                select(AdminSession).where(AdminSession.user_id == admin_id).order_by(AdminSession.last_seen_at.desc())
            )
        )
        .scalars()
        .all()
    )
    current_token = request.cookies.get(settings.webapi.session_cookie_name)
    return [
        AdminSessionRead.model_validate(r).model_copy(update={"is_current": r.session_id == current_token})
        for r in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: Annotated[int, Depends(require_super_admin)],
) -> None:
    """Revoke one of the calling admin's sessions. Refuse to revoke the current one."""
    current_token = request.cookies.get(settings.webapi.session_cookie_name)
    if session_id == current_token:
        raise HTTPException(status_code=400, detail="Use POST /api/auth/logout to end the current session")
    row = (
        await session.execute(select(AdminSession).where(AdminSession.session_id == session_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if row.user_id != admin_id:
        # Single-tenant — same admin set — but defensive guard if it ever expands.
        raise HTTPException(status_code=403, detail="Cannot revoke another user's session")
    await session_store.revoke_session(session, session_id)


@router.get("/system", response_model=SystemStatus)
async def get_system_status(
    request: Request,
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> SystemStatus:
    from app.core.container import container

    publish_bot = getattr(request.app.state, "publish_bot", None)
    return SystemStatus(
        super_admin_ids=list(settings.admin.super_admins),
        telethon_connected=container.get_telethon_client() is not None,
        publish_bot_ready=publish_bot is not None,
        allowed_origins=list(settings.webapi.allowed_origins),
        session_ttl_days=settings.webapi.session_ttl_days,
        feature_flags=[
            FeatureFlagRead(name="dev_bypass_auth", enabled=settings.webapi.dev_bypass_auth),
            FeatureFlagRead(name="moderation_enabled", enabled=settings.moderation.enabled),
            FeatureFlagRead(name="ad_detector_enabled", enabled=settings.moderation.ad_detector_enabled),
            FeatureFlagRead(name="assistant_bot_enabled", enabled=settings.assistant.enabled),
        ],
    )
