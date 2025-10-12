from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agent import AgentSession, ModelProvider, OpenRouterModel
from app.domain.repositories import IAgentRepository


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
        if provider == ModelProvider.OPENAI:
            return [
                OpenRouterModel(
                    id="gpt-4o",
                    name="GPT-4o",
                    description="Новейшая модель OpenAI с мультимодальными возможностями",
                    context_length=128000,
                ),
                OpenRouterModel(
                    id="gpt-4o-mini",
                    name="GPT-4o Mini",
                    description="Быстрая и экономичная версия GPT-4o",
                    context_length=128000,
                ),
                OpenRouterModel(
                    id="gpt-4-turbo",
                    name="GPT-4 Turbo",
                    description="Улучшенная версия GPT-4 с увеличенным контекстом",
                    context_length=128000,
                ),
            ]
        # provider == ModelProvider.OPENROUTER
        return [
            OpenRouterModel(
                id="anthropic/claude-sonnet-4.5",
                name="Claude Sonnet 4.5",
                description="Latest Claude model with enhanced capabilities",
                context_length=200000,
            ),
            OpenRouterModel(
                id="openai/gpt-5",
                name="GPT-5",
                description="OpenAI's latest flagship model",
                context_length=128000,
            ),
            OpenRouterModel(
                id="openai/gpt-5-mini",
                name="GPT-5 Mini",
                description="Fast and cost-effective GPT-5 variant",
                context_length=128000,
            ),
            OpenRouterModel(
                id="openai/gpt-5-chat",
                name="GPT-5 Chat",
                description="GPT-5 optimized for conversational tasks",
                context_length=128000,
            ),
            OpenRouterModel(
                id="openai/gpt-oss-20b",
                name="GPT OSS 20B",
                description="Open source 20B parameter model",
                context_length=32000,
            ),
            OpenRouterModel(
                id="x-ai/grok-4-fast",
                name="Grok 4 Fast",
                description="X.AI's fast and efficient Grok model",
                context_length=128000,
            ),
        ]


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
