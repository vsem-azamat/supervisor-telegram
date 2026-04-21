"""Test: TelethonStatsService caches results and degrades when telethon is absent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.webapi.services.telethon_stats import TelethonStatsService

pytestmark = pytest.mark.asyncio


async def test_member_count_returns_none_without_telethon() -> None:
    svc = TelethonStatsService(telethon=None)
    assert await svc.get_member_count(-100) is None


async def test_member_count_degrades_when_telethon_unavailable() -> None:
    tc = MagicMock()
    tc.is_available = False
    svc = TelethonStatsService(telethon=tc)
    assert await svc.get_member_count(-100) is None


async def test_member_count_calls_get_chat_info_once_and_caches() -> None:
    tc = MagicMock()
    tc.is_available = True
    chat_info = MagicMock(member_count=420)
    tc.get_chat_info = AsyncMock(return_value=chat_info)
    svc = TelethonStatsService(telethon=tc)

    first = await svc.get_member_count(-100)
    second = await svc.get_member_count(-100)

    assert first == 420
    assert second == 420
    tc.get_chat_info.assert_awaited_once_with(-100)


async def test_post_views_returns_empty_dict_without_telethon() -> None:
    svc = TelethonStatsService(telethon=None)
    assert await svc.get_post_views_batch(-100, [1, 2]) == {}


async def test_post_views_caches_per_chat_id_tuple() -> None:
    tc = MagicMock()
    tc.is_available = True
    tc.get_post_views = AsyncMock(return_value={1: 50})
    svc = TelethonStatsService(telethon=tc)

    first = await svc.get_post_views_batch(-100, [1])
    second = await svc.get_post_views_batch(-100, [1])

    assert first == {1: 50}
    assert second == {1: 50}
    tc.get_post_views.assert_awaited_once()
