from abc import ABC, abstractmethod

from app.agent_platform.domain.agent import AgentSession, ModelProvider, OpenRouterModel


class IAgentRepository(ABC):
    """Agent repository interface."""

    @abstractmethod
    async def save_session(self, session: AgentSession) -> AgentSession:
        """Save agent session."""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> AgentSession | None:
        """Get agent session by ID."""
        pass

    @abstractmethod
    async def get_user_sessions(self, user_id: int, limit: int = 20) -> list[AgentSession]:
        """Get user's agent sessions."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete agent session."""
        pass

    @abstractmethod
    async def update_session(self, session: AgentSession) -> AgentSession:
        """Update agent session."""
        pass

    @abstractmethod
    async def get_available_models(self, provider: ModelProvider) -> list[OpenRouterModel]:
        """Get available models for provider."""
        pass
