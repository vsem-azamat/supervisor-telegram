"""Tests for webapi dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core.config import settings
from app.webapi.deps import require_super_admin
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

pytestmark = pytest.mark.asyncio


def _fake_request(cookie: str | None = None) -> StarletteRequest:
    """Minimal Starlette Request for direct-call dependency tests."""
    headers = []
    if cookie is not None:
        headers.append((b"cookie", f"{settings.webapi.session_cookie_name}={cookie}".encode()))
    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""}
    return StarletteRequest(scope)


def _fake_session() -> AsyncMock:
    """Placeholder session for direct-call dependency tests."""
    return AsyncMock()


async def test_require_super_admin_requires_cookie(override_super_admins) -> None:
    settings.admin.super_admins = [12345, 67890]

    with pytest.raises(HTTPException) as exc_info:
        await require_super_admin(_fake_request(), _fake_session())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "not authenticated"


async def test_require_super_admin_returns_valid_session_user(
    monkeypatch: pytest.MonkeyPatch,
    override_super_admins,
) -> None:
    settings.admin.super_admins = [12345, 67890]

    async def _load_valid_session(session: AsyncMock, session_id: str) -> SimpleNamespace:
        assert session_id == "session-token"
        return SimpleNamespace(user_id=67890)

    monkeypatch.setattr(
        "app.webapi.auth.session_store.load_valid_session",
        _load_valid_session,
    )

    result = await require_super_admin(_fake_request("session-token"), _fake_session())

    assert result == 67890


async def test_require_super_admin_raises_when_none_configured(override_super_admins) -> None:
    """With zero super_admins there is no identity to attach — the dep
    rejects the request so endpoints never run without an admin context."""
    settings.admin.super_admins = []

    with pytest.raises(HTTPException) as exc_info:
        await require_super_admin(_fake_request(), _fake_session())

    assert exc_info.value.status_code == 503
    assert "super_admin" in exc_info.value.detail.lower()
