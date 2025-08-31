"""Repository factory for creating repository instances."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories import (
    IAdminRepository,
    IAgentRepository,
    IChatLinkRepository,
    IChatRepository,
    IMessageRepository,
    IUserRepository,
)
from app.infrastructure.db.repositories.admin import AdminRepository
from app.infrastructure.db.repositories.agent import InMemoryAgentRepository
from app.infrastructure.db.repositories.chat import ChatRepository
from app.infrastructure.db.repositories.chat_link import ChatLinkRepository
from app.infrastructure.db.repositories.message import MessageRepository
from app.infrastructure.db.repositories.user import UserRepository


class RepositoryFactory:
    """Factory for creating repository instances."""

    _agent_repository_singleton: IAgentRepository | None = None

    @classmethod
    def create_user_repository(cls, session: AsyncSession) -> IUserRepository:
        """Create user repository."""
        return UserRepository(session)

    @classmethod
    def create_chat_repository(cls, session: AsyncSession) -> IChatRepository:
        """Create chat repository."""
        return ChatRepository(session)

    @classmethod
    def create_admin_repository(cls, session: AsyncSession) -> IAdminRepository:
        """Create admin repository."""
        return AdminRepository(session)

    @classmethod
    def create_message_repository(cls, session: AsyncSession) -> IMessageRepository:
        """Create message repository."""
        return MessageRepository(session)

    @classmethod
    def create_chat_link_repository(cls, session: AsyncSession) -> IChatLinkRepository:
        """Create chat link repository."""
        return ChatLinkRepository(session)

    @classmethod
    def get_agent_repository(cls) -> IAgentRepository:
        """Get agent repository (singleton for in-memory)."""
        if cls._agent_repository_singleton is None:
            cls._agent_repository_singleton = InMemoryAgentRepository()
        return cls._agent_repository_singleton

    @classmethod
    def reset_agent_repository(cls) -> None:
        """Reset agent repository singleton (useful for testing)."""
        cls._agent_repository_singleton = None
