"""Shared E2E test fixtures.

db_engine and db_session_maker are inherited from root conftest.py.
"""

import pytest_asyncio

from tests.fake_telegram import FakeTelegramServer


@pytest_asyncio.fixture()
async def fake_tg():
    """Start fake Telegram server."""
    async with FakeTelegramServer() as server:
        yield server
