"""Agent memory — decision logging to Postgres."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import AgentEvent
from app.domain.models import AgentDecision


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
