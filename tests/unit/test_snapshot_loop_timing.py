"""When the loop tries again.

The client connects from the dispatcher's startup hook while the loop is
started alongside polling, so the first tick arrives before Telegram has been
reached. Sleeping the full hour on that leaves the table empty for an hour
after every deploy — and an empty table for an hour is exactly what a broken
loop looks like, which is how the last one hid.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.telethon import snapshots

pytestmark = pytest.mark.unit


class _StopLoopError(Exception):
    """Breaks the forever-loop once the test has seen what it came for."""


def _client(available: bool) -> MagicMock:
    client = MagicMock()
    client.is_available = available
    return client


async def _run_until_first_sleep(monkeypatch, telethon) -> float:
    """Run the loop until it first sleeps, and return how long for."""
    slept: list[float] = []

    async def _sleep(seconds: float) -> None:
        slept.append(seconds)
        raise _StopLoopError

    monkeypatch.setattr(snapshots.asyncio, "sleep", _sleep)
    with pytest.raises(_StopLoopError):
        await snapshots.run_snapshot_loop(
            session_maker=MagicMock(),
            telethon=telethon,
            interval_seconds=3600,
            retry_seconds=30,
        )
    return slept[0]


async def test_it_retries_soon_when_not_connected_yet(monkeypatch) -> None:
    assert await _run_until_first_sleep(monkeypatch, _client(available=False)) == 30


async def test_it_waits_the_full_interval_after_a_tick(monkeypatch) -> None:
    monkeypatch.setattr(snapshots, "snapshot_once", AsyncMock(return_value=3))

    assert await _run_until_first_sleep(monkeypatch, _client(available=True)) == 3600


async def test_a_missing_client_is_not_a_crash(monkeypatch) -> None:
    """Telethon unconfigured is a deployment choice, not a fault."""
    assert await _run_until_first_sleep(monkeypatch, None) == 30


async def test_it_does_not_call_telegram_before_it_can(monkeypatch) -> None:
    once = AsyncMock()
    monkeypatch.setattr(snapshots, "snapshot_once", once)

    await _run_until_first_sleep(monkeypatch, _client(available=False))

    once.assert_not_awaited()


async def test_a_failed_tick_still_waits_the_full_interval(monkeypatch) -> None:
    """A raising tick must not become a hot retry against Telegram."""
    monkeypatch.setattr(snapshots, "snapshot_once", AsyncMock(side_effect=RuntimeError("boom")))

    assert await _run_until_first_sleep(monkeypatch, _client(available=True)) == 3600
