"""Authentication routes: Telegram Login Widget -> session cookie."""

from __future__ import annotations

import asyncio
import time
from functools import cache
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db import magic_link_store
from app.webapi.auth import session_store
from app.webapi.auth.telegram_login import LoginWidgetError, verify_login_payload
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import AuthConfigResponse, AuthMeResponse, MagicLinkLoginPayload, TelegramLoginPayload

logger = get_logger("webapi.auth")
router = APIRouter(prefix="/auth", tags=["auth"])
_login_bot_username_cache: str | None = None
_login_bot_username_cache_set = False
_login_bot_username_failure_retry_after = 0.0
_login_bot_username_lock = asyncio.Lock()
_LOGIN_BOT_USERNAME_FAILURE_TTL_SECONDS = 60.0


async def _fetch_login_bot_username() -> str | None:
    from aiogram import Bot

    bot = Bot(token=settings.telegram.token)
    try:
        me = await bot.get_me()
        username = (me.username or "").strip().removeprefix("@")
        return username or None
    finally:
        await bot.session.close()


def _clear_login_bot_username_cache() -> None:
    global _login_bot_username_cache, _login_bot_username_cache_set, _login_bot_username_failure_retry_after

    _login_bot_username_cache = None
    _login_bot_username_cache_set = False
    _login_bot_username_failure_retry_after = 0.0


async def _login_bot_username() -> str | None:
    global _login_bot_username_cache, _login_bot_username_cache_set, _login_bot_username_failure_retry_after

    if _login_bot_username_cache_set:
        return _login_bot_username_cache
    now = time.monotonic()
    if now < _login_bot_username_failure_retry_after:
        return None
    async with _login_bot_username_lock:
        if not _login_bot_username_cache_set:
            now = time.monotonic()
            if now < _login_bot_username_failure_retry_after:
                return None
            try:
                _login_bot_username_cache = await _fetch_login_bot_username()
            except Exception as err:
                logger.warning("login_bot_username_resolve_failed", error=str(err))
                _login_bot_username_failure_retry_after = now + _LOGIN_BOT_USERNAME_FAILURE_TTL_SECONDS
                return None
            else:
                _login_bot_username_cache_set = True
                _login_bot_username_failure_retry_after = 0.0
    return _login_bot_username_cache


def _login_start_payload() -> str | None:
    payload = settings.webapi.login_start_payload.strip()
    return payload or None


@cache
def _bot_start_url(username: str, payload: str) -> str:
    return f"https://t.me/{username}?start={payload}"


@router.get("/config", response_model_exclude_none=True)
async def auth_config() -> AuthConfigResponse:
    username = await _login_bot_username()
    payload = _login_start_payload()
    bot_start_url = None
    if settings.webapi.auth_mode == "magic_link" and username and payload:
        bot_start_url = _bot_start_url(username, payload)
    return AuthConfigResponse(
        auth_mode=settings.webapi.auth_mode,
        bot_username=username,
        bot_start_url=bot_start_url,
    )


@router.post("/login")
async def login(
    payload: TelegramLoginPayload,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthMeResponse:
    if settings.webapi.auth_mode != "telegram":
        raise HTTPException(status_code=404, detail="telegram login disabled")

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
    return AuthMeResponse(user_id=user_id, auth_mode=settings.webapi.auth_mode)


@router.post("/magic-link")
async def magic_link_login(
    payload: MagicLinkLoginPayload,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthMeResponse:
    if settings.webapi.auth_mode != "magic_link":
        raise HTTPException(status_code=404, detail="magic link login disabled")
    if not settings.admin.super_admins:
        raise HTTPException(status_code=503, detail="No super_admin configured")

    user_id = await magic_link_store.consume_magic_link(session, payload.token)
    main_admin_id = settings.admin.super_admins[0]
    if user_id is None or user_id != main_admin_id:
        logger.warning("magic_link_rejected", ip=request.client.host if request.client else None)
        raise HTTPException(status_code=401, detail="login failed")

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
    return AuthMeResponse(user_id=user_id, auth_mode=settings.webapi.auth_mode)


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
    return AuthMeResponse(user_id=user_id, auth_mode=settings.webapi.auth_mode)
