from app.agent_platform.domain.agent import AgentSession, ModelProvider, OpenRouterModel
from app.agent_platform.domain.agent_models import get_models_by_provider
from app.agent_platform.domain.repositories import IAgentRepository
from sqlalchemy.ext.asyncio import AsyncSession


class InMemoryAgentRepository(IAgentRepository):
    """In-memory implementation of agent repository for deployment without database."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    async def save_session(self, session: AgentSession) -> AgentSession:
        """Save agent session."""
        self._sessions[session.id] = session
        return session

    async def get_session(self, session_id: str) -> AgentSession | None:
        """Get agent session by ID."""
        return self._sessions.get(session_id)

    async def get_user_sessions(self, user_id: int, limit: int = 20) -> list[AgentSession]:
        """Get user's agent sessions."""
        user_sessions = [
            session for session in self._sessions.values() if session.user_id.value == user_id and session.is_active
        ]
        # Sort by update time (newest first)
        user_sessions.sort(key=lambda x: x.updated_at, reverse=True)
        return user_sessions[:limit]

    async def delete_session(self, session_id: str) -> bool:
        """Delete agent session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def update_session(self, session: AgentSession) -> AgentSession:
        """Update agent session."""
        if session.id in self._sessions:
            self._sessions[session.id] = session
            return session
        raise ValueError(f"Session {session.id} not found")

    async def get_available_models(self, provider: ModelProvider) -> list[OpenRouterModel]:
        """Get available models for provider."""
        return get_models_by_provider(provider)


# TODO: Full PostgreSQL implementation will be added later
class SQLAgentRepository(IAgentRepository):
    """SQL-based implementation of agent repository (planned)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        # Use in-memory as fallback for now
        self._fallback = InMemoryAgentRepository()

    async def save_session(self, session: AgentSession) -> AgentSession:
        return await self._fallback.save_session(session)

    async def get_session(self, session_id: str) -> AgentSession | None:
        return await self._fallback.get_session(session_id)

    async def get_user_sessions(self, user_id: int, limit: int = 20) -> list[AgentSession]:
        return await self._fallback.get_user_sessions(user_id, limit)

    async def delete_session(self, session_id: str) -> bool:
        return await self._fallback.delete_session(session_id)

    async def update_session(self, session: AgentSession) -> AgentSession:
        return await self._fallback.update_session(session)

    async def get_available_models(self, provider: ModelProvider) -> list[OpenRouterModel]:
        return await self._fallback.get_available_models(provider)
