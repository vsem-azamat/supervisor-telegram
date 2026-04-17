"""Agent memory — decision logging and retrieval from Postgres."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.db.models import AgentDecision

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.moderation.schemas import AgentEvent


@dataclass
class UserRiskProfile:
    """Aggregate risk signals for a user."""

    total_reports: int
    distinct_reporters: int
    distinct_chats: int
    actions_taken: dict[str, int]  # action -> count
    overridden_count: int  # times admin overrode agent's decision
    last_action: str | None


class AgentMemory:
    """Stores and retrieves agent decisions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log_decision(
        self,
        event: AgentEvent,
        action: str,
        reason: str,
        admin_override: str | None = None,
    ) -> AgentDecision:
        decision = AgentDecision(
            event_type=event.event_type,
            chat_id=event.chat_id,
            message_id=event.message_id,
            target_user_id=event.target_user_id,
            reporter_id=event.reporter_id,
            message_text=event.target_message_text,
            action=action,
            reason=reason,
            admin_override=admin_override,
        )
        self.db.add(decision)
        await self.db.commit()
        await self.db.refresh(decision)
        return decision

    async def set_admin_override(self, decision_id: int, override_action: str) -> None:
        """Record that an admin overrode the agent's decision."""
        stmt = select(AgentDecision).where(AgentDecision.id == decision_id)
        result = await self.db.execute(stmt)
        decision = result.scalar_one_or_none()
        if decision:
            decision.admin_override = override_action
            await self.db.commit()

    async def get_user_history(self, user_id: int, limit: int = 10) -> list[AgentDecision]:
        """Get recent decisions about a user."""
        stmt = (
            select(AgentDecision)
            .where(AgentDecision.target_user_id == user_id)
            .order_by(AgentDecision.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_chat_history(self, chat_id: int, limit: int = 20) -> list[AgentDecision]:
        """Get recent decisions in a chat."""
        stmt = (
            select(AgentDecision)
            .where(AgentDecision.chat_id == chat_id)
            .order_by(AgentDecision.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_corrections(self, limit: int = 10) -> list[AgentDecision]:
        """Get recent decisions where admin overrode the agent — learning signal."""
        stmt = (
            select(AgentDecision)
            .where(AgentDecision.admin_override.is_not(None))
            .order_by(AgentDecision.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_risk_profile(self, user_id: int) -> UserRiskProfile:
        """Build aggregate risk profile for a user."""
        base = select(AgentDecision).where(AgentDecision.target_user_id == user_id)

        # Total reports
        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(total_stmt)).scalar() or 0

        # Distinct reporters
        reporters_stmt = select(func.count(func.distinct(AgentDecision.reporter_id))).where(
            AgentDecision.target_user_id == user_id,
            AgentDecision.reporter_id.is_not(None),
        )
        distinct_reporters = (await self.db.execute(reporters_stmt)).scalar() or 0

        # Distinct chats
        chats_stmt = select(func.count(func.distinct(AgentDecision.chat_id))).where(
            AgentDecision.target_user_id == user_id,
        )
        distinct_chats = (await self.db.execute(chats_stmt)).scalar() or 0

        # Action breakdown
        action_stmt = (
            select(AgentDecision.action, func.count())
            .where(AgentDecision.target_user_id == user_id)
            .group_by(AgentDecision.action)
        )
        action_rows = (await self.db.execute(action_stmt)).all()
        actions_taken = {row[0]: row[1] for row in action_rows}

        # Override count
        override_stmt = select(func.count()).where(
            AgentDecision.target_user_id == user_id,
            AgentDecision.admin_override.is_not(None),
        )
        overridden = (await self.db.execute(override_stmt)).scalar() or 0

        # Last action
        last_stmt = (
            select(AgentDecision.action)
            .where(AgentDecision.target_user_id == user_id)
            .order_by(AgentDecision.created_at.desc())
            .limit(1)
        )
        last_action = (await self.db.execute(last_stmt)).scalar()

        return UserRiskProfile(
            total_reports=total,
            distinct_reporters=distinct_reporters,
            distinct_chats=distinct_chats,
            actions_taken=actions_taken,
            overridden_count=overridden,
            last_action=last_action,
        )
