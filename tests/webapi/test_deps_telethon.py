"""Test: get_telethon dependency returns container's telethon_client or None."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app.webapi.deps import get_telethon


@pytest.mark.asyncio
async def test_returns_none_when_container_empty(monkeypatch) -> None:
    from app.core.container import container

    monkeypatch.setattr(container, "_telethon_client", None, raising=False)
    result = await get_telethon()
    assert result is None


@pytest.mark.asyncio
async def test_returns_container_client(monkeypatch) -> None:
    from app.core.container import container

    fake = MagicMock(name="telethon_client")
    monkeypatch.setattr(container, "get_telethon_client", lambda: fake)
    result = await get_telethon()
    assert result is fake
