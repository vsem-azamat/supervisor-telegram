"""Costs — session summary + persistent history."""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.cost_tracker import get_session_summary
from app.core.time import utc_now
from app.db.models import CostEvent
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import CostHistoryDay, CostHistoryResponse, SessionCostSummary

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/session", response_model=SessionCostSummary)
async def session_cost(
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> SessionCostSummary:
    return SessionCostSummary.from_tracker(get_session_summary())


@router.get("/history", response_model=CostHistoryResponse)
async def cost_history(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
) -> CostHistoryResponse:
    """Daily aggregate of cost_events for the last ``days`` days, oldest first.

    Empty days are filled with zero rows so the FE can render a contiguous
    sparkline without gap-filling client-side.
    """
    cutoff = utc_now() - datetime.timedelta(days=days)
    day_col = func.date(CostEvent.occurred_at).label("day")
    rows = (
        await session.execute(
            select(
                day_col,
                func.sum(CostEvent.cost_usd).label("cost_usd"),
                func.sum(CostEvent.total_tokens).label("tokens"),
                func.count(CostEvent.id).label("calls"),
                func.sum(CostEvent.cache_savings_usd).label("savings"),
            )
            .where(CostEvent.occurred_at >= cutoff)
            .group_by(day_col)
            .order_by(day_col)
        )
    ).all()
    by_day: dict[str, CostHistoryDay] = {}
    for row in rows:
        # SQLite returns string, PG returns date — normalise.
        day_value = row.day.isoformat() if hasattr(row.day, "isoformat") else str(row.day)
        by_day[day_value] = CostHistoryDay(
            day=day_value,
            cost_usd=float(row.cost_usd or 0.0),
            tokens=int(row.tokens or 0),
            calls=int(row.calls or 0),
            cache_savings_usd=float(row.savings or 0.0),
        )

    today = utc_now().date()
    series: list[CostHistoryDay] = []
    for offset in range(days - 1, -1, -1):
        d = (today - datetime.timedelta(days=offset)).isoformat()
        series.append(
            by_day.get(
                d,
                CostHistoryDay(day=d, cost_usd=0.0, tokens=0, calls=0, cache_savings_usd=0.0),
            )
        )
    total_cost = sum(s.cost_usd for s in series)
    total_calls = sum(s.calls for s in series)
    total_tokens = sum(s.tokens for s in series)
    return CostHistoryResponse(
        days=days,
        series=series,
        total_cost_usd=round(total_cost, 6),
        total_calls=total_calls,
        total_tokens=total_tokens,
    )
