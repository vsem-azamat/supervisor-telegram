"""Authentication routes: Telegram Login Widget -> session cookie."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.webapi.auth import session_store
from app.webapi.auth.telegram_login import LoginWidgetError, verify_login_payload
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import AuthMeResponse, TelegramLoginPayload

logger = get_logger("webapi.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    payload: TelegramLoginPayload,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthMeResponse:
    # Dump dict with extras so HMAC sees the whole payload.
    raw = {k: str(v) for k, v in payload.model_dump().items()}
    try:
        user_id = verify_login_payload(raw, bot_token=settings.telegram.token)
    except LoginWidgetError as err:
        logger.warning("login_widget_rejected", reason=str(err))
        raise HTTPException(status_code=401, detail="login failed") from err

    if user_id not in settings.admin.super_admins:
        logger.warning("login_non_admin", user_id=user_id)
        raise HTTPException(status_code=403, detail="not authorized")

    row = await session_store.create_session(
        session,
        user_id=user_id,
        ttl_days=settings.webapi.session_ttl_days,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    response.set_cookie(
        key=settings.webapi.session_cookie_name,
        value=row.session_id,
        max_age=settings.webapi.session_ttl_days * 86400,
        secure=settings.webapi.session_cookie_secure,
        httponly=True,
        samesite=cast("Literal['lax', 'strict', 'none']", settings.webapi.session_cookie_samesite),
        path="/",
    )
    return AuthMeResponse(user_id=user_id)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    token = request.cookies.get(settings.webapi.session_cookie_name)
    if token:
        await session_store.revoke_session(session, token)
    response.delete_cookie(settings.webapi.session_cookie_name, path="/")


@router.get("/me")
async def me(user_id: Annotated[int, Depends(require_super_admin)]) -> AuthMeResponse:
    return AuthMeResponse(user_id=user_id)
