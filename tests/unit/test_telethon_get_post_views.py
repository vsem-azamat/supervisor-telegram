"""Unit test: TelethonClient.get_post_views degrades gracefully and maps views."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core.config import TelethonSettings
from app.telethon.telethon_client import TelethonClient

pytestmark = pytest.mark.asyncio


async def test_returns_empty_when_disabled() -> None:
    settings = TelethonSettings(enabled=False, api_id=1, api_hash="x", session_name="s", phone=None)
    client = TelethonClient(settings=settings)

    result = await client.get_post_views(-100, [1, 2, 3])

    assert result == {}


async def test_returns_view_map_when_connected() -> None:
    settings = TelethonSettings(enabled=True, api_id=1, api_hash="x", session_name="s", phone=None)
    client = TelethonClient(settings=settings)
    client._connected = True  # pretend connected
    fake_client = MagicMock()
    fake_client.get_messages = AsyncMock(
        return_value=[
            MagicMock(id=1, views=100),
            MagicMock(id=2, views=250),
            None,  # Telegram returns None for missing IDs
        ]
    )
    client._client = fake_client

    result = await client.get_post_views(-100, [1, 2, 3])

    assert result == {1: 100, 2: 250}
