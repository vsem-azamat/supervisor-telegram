"""Tests for webapi dependencies."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.core.config import settings
from app.webapi.deps import require_super_admin
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

pytestmark = pytest.mark.asyncio


def _fake_request() -> StarletteRequest:
    """Minimal Starlette Request for direct-call dep tests (bypass path never
    reads cookies, so scope contents don't matter)."""
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""}
    return StarletteRequest(scope)


def _fake_session() -> AsyncMock:
    """Placeholder session — bypass path never touches the DB."""
    return AsyncMock()


async def test_require_super_admin_returns_first_configured(override_super_admins) -> None:
    """In dev the dep returns the first configured super_admin — enough
    for downstream code to treat the request as authenticated."""
    settings.admin.super_admins = [12345, 67890]

    result = await require_super_admin(_fake_request(), _fake_session())

    assert result == 12345


async def test_require_super_admin_raises_when_none_configured(override_super_admins) -> None:
    """With zero super_admins there is no identity to attach — the dep
    rejects the request so endpoints never run without an admin context."""
    settings.admin.super_admins = []

    with pytest.raises(HTTPException) as exc_info:
        await require_super_admin(_fake_request(), _fake_session())

    assert exc_info.value.status_code == 503
    assert "super_admin" in exc_info.value.detail.lower()
