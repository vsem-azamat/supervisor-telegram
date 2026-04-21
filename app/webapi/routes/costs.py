"""Costs — session summary from in-memory cost_tracker."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.channel.cost_tracker import get_session_summary
from app.webapi.deps import require_super_admin
from app.webapi.schemas import SessionCostSummary

router = APIRouter(prefix="/costs", tags=["costs"])


@router.get("/session", response_model=SessionCostSummary)
async def session_cost(
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> SessionCostSummary:
    return SessionCostSummary.from_tracker(get_session_summary())
