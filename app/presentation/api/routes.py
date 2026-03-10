"""aiohttp routes for the webapp stats API."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.presentation.api.auth import generate_magic_link, validate_token
from app.presentation.api.stats import get_all_channels_stats, get_channel_stats, get_recent_posts, get_sources

_SESSION_MAKER_KEY: web.AppKey[async_sessionmaker[AsyncSession]] = web.AppKey("session_maker", async_sessionmaker)
_ALLOWED_EMAILS_KEY: web.AppKey[list[str]] = web.AppKey("allowed_emails", list)
_ALLOWED_ORIGINS_KEY: web.AppKey[list[str]] = web.AppKey("allowed_origins", list)
_MAX_API_PAGE_SIZE = 100


def _json_response(data: object, *, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
    )


def _error(msg: str, status: int = 400) -> web.Response:
    return _json_response({"error": msg}, status=status)


def _get_bearer_token(request: web.Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _require_auth(request: web.Request) -> dict[str, str] | web.Response:
    """Validate bearer token. Returns user dict or an error Response."""
    token = _get_bearer_token(request)
    if not token:
        return _error("Missing Authorization header", status=401)
    user = validate_token(token)
    if user is None:
        return _error("Invalid or expired token", status=401)
    return user


def _session_maker(request: web.Request) -> async_sessionmaker[AsyncSession]:
    return request.app[_SESSION_MAKER_KEY]


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


async def handle_magic_link(request: web.Request) -> web.Response:
    """POST /api/auth/magic-link  —  generate a magic-link token."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception):
        return _error("Invalid JSON body")

    email = body.get("email")
    if not email or not isinstance(email, str):
        return _error("email is required")

    allowed: list[str] = request.app[_ALLOWED_EMAILS_KEY]
    if email not in allowed:
        return _error("Email not allowed", status=403)

    # Role is determined server-side based on email — never from the request body.
    # All magic-link users get "viewer" role. Admin roles should be granted
    # via a separate admin_emails configuration if needed in the future.
    role = "viewer"

    token = generate_magic_link(email, role=role)
    return _json_response({"token": token, "email": email, "role": role}, status=201)


async def handle_verify(request: web.Request) -> web.Response:
    """GET /api/auth/verify?token=...  —  verify a magic-link token."""
    token = request.query.get("token", "")
    if not token:
        return _error("token query parameter required")

    user = validate_token(token)
    if user is None:
        return _error("Invalid or expired token", status=401)

    return _json_response({"authenticated": True, "token": token, **user})


# ---------------------------------------------------------------------------
# Stats endpoints
# ---------------------------------------------------------------------------


async def handle_channels_list(request: web.Request) -> web.Response:
    """GET /api/stats/channels  —  all channels with aggregated stats."""
    auth = _require_auth(request)
    if isinstance(auth, web.Response):
        return auth

    data = await get_all_channels_stats(_session_maker(request))
    return _json_response(data)


async def handle_channel_posts(request: web.Request) -> web.Response:
    """GET /api/stats/channels/{channel_id}/posts"""
    auth = _require_auth(request)
    if isinstance(auth, web.Response):
        return auth

    channel_id = request.match_info["channel_id"]
    try:
        limit = min(int(request.query.get("limit", "20")), _MAX_API_PAGE_SIZE)
    except ValueError:
        limit = 20
    data = await get_recent_posts(_session_maker(request), channel_id, limit=limit)
    return _json_response(data)


async def handle_channel_sources(request: web.Request) -> web.Response:
    """GET /api/stats/channels/{channel_id}/sources"""
    auth = _require_auth(request)
    if isinstance(auth, web.Response):
        return auth

    channel_id = request.match_info["channel_id"]
    data = await get_sources(_session_maker(request), channel_id)
    return _json_response(data)


async def handle_channel_detail(request: web.Request) -> web.Response:
    """GET /api/stats/channels/{channel_id}  —  single channel stats."""
    auth = _require_auth(request)
    if isinstance(auth, web.Response):
        return auth

    channel_id = request.match_info["channel_id"]
    data = await get_channel_stats(_session_maker(request), channel_id)
    return _json_response(data)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def cors_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
    """Add CORS headers, restricted to explicitly allowed origins."""
    origin = request.headers.get("Origin", "")
    allowed_origins: list[str] = request.app.get(_ALLOWED_ORIGINS_KEY, [])

    # Determine if origin is allowed
    allow_origin = origin if origin in allowed_origins else ""

    # Handle CORS preflight
    if request.method == "OPTIONS":
        resp = web.Response(status=204)
        if allow_origin:
            resp.headers["Access-Control-Allow-Origin"] = allow_origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Max-Age"] = "3600"
        return resp

    response = await handler(request)
    if allow_origin:
        response.headers["Access-Control-Allow-Origin"] = allow_origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    return response


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_api_app(
    session_maker: async_sessionmaker[AsyncSession],
    allowed_emails: list[str] | None = None,
    allowed_origins: list[str] | None = None,
) -> web.Application:
    """Build and return the aiohttp Application with all routes registered."""
    app = web.Application(middlewares=[cors_middleware])
    app[_SESSION_MAKER_KEY] = session_maker
    app[_ALLOWED_EMAILS_KEY] = allowed_emails or []
    app[_ALLOWED_ORIGINS_KEY] = allowed_origins or []

    app.router.add_post("/api/auth/magic-link", handle_magic_link)
    app.router.add_get("/api/auth/verify", handle_verify)
    app.router.add_get("/api/stats/channels", handle_channels_list)
    app.router.add_get("/api/stats/channels/{channel_id}", handle_channel_detail)
    app.router.add_get("/api/stats/channels/{channel_id}/posts", handle_channel_posts)
    app.router.add_get("/api/stats/channels/{channel_id}/sources", handle_channel_sources)

    return app
