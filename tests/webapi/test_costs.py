"""Tests for /api/costs endpoints."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.channel import cost_tracker
from app.channel.cost_tracker import LLMUsage
from app.core.config import settings
from app.core.time import utc_now
from app.db.models import CostEvent
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def history_client(db_session_maker: async_sessionmaker[AsyncSession]):
    """Wire test session for /history queries — it touches cost_events table."""
    from app.webapi.deps import get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    settings.admin.super_admins = [1]
    settings.webapi.dev_bypass_auth = True
    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    yield AsyncClient(transport=transport, base_url="http://test")
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture(autouse=True)
def _clean_cost_history():
    cost_tracker.reset_usage_history()
    yield
    cost_tracker.reset_usage_history()


async def test_session_cost_empty_when_no_usage(client) -> None:
    async with client as c:
        resp = await c.get("/api/costs/session")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 0
    assert body["total_cost_usd"] == 0.0
    assert body["by_operation"] == []


async def test_session_cost_aggregates_by_operation(client) -> None:
    await cost_tracker.log_usage(
        LLMUsage(
            model="m-a",
            operation="screening",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=0.01,
        )
    )
    await cost_tracker.log_usage(
        LLMUsage(
            model="m-a",
            operation="screening",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            estimated_cost_usd=0.02,
        )
    )
    await cost_tracker.log_usage(
        LLMUsage(
            model="m-b",
            operation="generation",
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            estimated_cost_usd=0.005,
        )
    )

    async with client as c:
        resp = await c.get("/api/costs/session")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 3
    assert pytest.approx(body["total_cost_usd"], abs=1e-6) == 0.035
    assert body["total_tokens"] == 525

    ops = {b["operation"]: b for b in body["by_operation"]}
    assert ops["screening"]["calls"] == 2
    assert pytest.approx(ops["screening"]["cost_usd"], abs=1e-6) == 0.03
    assert ops["screening"]["tokens"] == 450
    assert ops["generation"]["calls"] == 1


async def test_cost_history_returns_zero_filled_series(history_client) -> None:
    async with history_client as c:
        resp = await c.get("/api/costs/history?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"] == 7
    assert len(body["series"]) == 7
    assert body["total_calls"] == 0
    assert all(p["cost_usd"] == 0.0 for p in body["series"])


async def test_cost_history_aggregates_persisted_events(history_client, db_session_maker) -> None:
    now = utc_now()
    async with db_session_maker() as s:
        s.add_all(
            [
                CostEvent(
                    model="m-a",
                    operation="screening",
                    occurred_at=now - datetime.timedelta(hours=1),
                    total_tokens=100,
                    cost_usd=0.05,
                ),
                CostEvent(
                    model="m-a",
                    operation="generation",
                    occurred_at=now - datetime.timedelta(hours=2),
                    total_tokens=200,
                    cost_usd=0.10,
                ),
                CostEvent(
                    model="m-b",
                    operation="discovery",
                    occurred_at=now - datetime.timedelta(days=2, hours=1),
                    total_tokens=50,
                    cost_usd=0.02,
                ),
                # Outside window:
                CostEvent(
                    model="m-c",
                    operation="screening",
                    occurred_at=now - datetime.timedelta(days=10),
                    total_tokens=500,
                    cost_usd=1.00,
                ),
            ]
        )
        await s.commit()

    async with history_client as c:
        resp = await c.get("/api/costs/history?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"] == 7
    assert len(body["series"]) == 7
    # 0.05 + 0.10 (today) + 0.02 (2d ago) — 1.00 falls outside the 7-day window.
    assert pytest.approx(body["total_cost_usd"], abs=1e-6) == 0.17
    assert body["total_calls"] == 3
    assert body["total_tokens"] == 350
