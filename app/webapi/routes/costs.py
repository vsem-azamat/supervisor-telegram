"""Costs — session summary from in-memory cost_tracker."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.channel.cost_tracker import get_session_summary
from app.webapi.deps import require_super_admin
from app.webapi.schemas import OperationCostBucket, SessionCostSummary

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/session", response_model=SessionCostSummary)
async def session_cost(
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> SessionCostSummary:
    summary = get_session_summary()
    buckets = [
        OperationCostBucket(
            operation=op_name,
            tokens=int(data.get("tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            calls=int(data.get("calls", 0)),
            cache_savings_usd=float(data.get("cache_savings_usd", 0.0)),
        )
        for op_name, data in (summary.get("by_operation") or {}).items()
    ]
    return SessionCostSummary(
        total_tokens=int(summary.get("total_tokens", 0)),
        total_cost_usd=float(summary.get("total_cost_usd", 0.0)),
        total_calls=int(summary.get("total_calls", 0)),
        cache_read_tokens=int(summary.get("cache_read_tokens", 0)),
        cache_write_tokens=int(summary.get("cache_write_tokens", 0)),
        cache_savings_usd=float(summary.get("cache_savings_usd", 0.0)),
        by_operation=buckets,
    )
