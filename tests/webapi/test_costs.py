"""Tests for /api/costs endpoints."""

from __future__ import annotations

import pytest
from app.channel import cost_tracker
from app.channel.cost_tracker import LLMUsage
from app.core.config import settings
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    settings.admin.super_admins = [1]
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


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
