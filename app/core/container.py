"""Dependency injection container."""

from typing import TypeVar

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.moderation_service import ModerationService
from app.application.services.spam import SpamService
from app.application.services.user_service import UserService
from app.core.repository_factory import RepositoryFactory
from app.core.service_registry import ServiceRegistry
from app.domain.repositories import (
    IAdminRepository,
    IChatLinkRepository,
    IChatRepository,
    IMessageRepository,
    IUserRepository,
)

T = TypeVar("T")


class Container:
    """Dependency injection container."""

    def __init__(self) -> None:
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        self._bot: Bot | None = None
        self._service_registry: ServiceRegistry | None = None
        self._repository_factory: RepositoryFactory | None = None

    def _get_service_registry(self) -> ServiceRegistry:
        """Get or create service registry."""
        if not self._service_registry:
            if not self._session_maker:
                raise ValueError("Session maker not set")
            self._service_registry = ServiceRegistry(self._session_maker, self._bot)
        return self._service_registry

    def _get_repository_factory(self) -> RepositoryFactory:
        """Get or create repository factory."""
        if not self._repository_factory:
            self._repository_factory = RepositoryFactory()
        return self._repository_factory

    def set_session_maker(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        """Set database session maker."""
        self._session_maker = session_maker

    def set_bot(self, bot: Bot) -> None:
        """Set bot instance."""
        self._bot = bot

    def get(self, interface: type[T]) -> T:
        """Get service instance."""
        service_registry = self._get_service_registry()
        return service_registry.get(interface)

    def get_session(self) -> AsyncSession:
        """Get database session."""
        if not self._session_maker:
            raise ValueError("Session maker not set")
        return self._session_maker()

    def get_bot(self) -> Bot:
        """Get bot instance."""
        if not self._bot:
            raise ValueError("Bot not set")
        return self._bot

    def get_user_repository(self, session: AsyncSession) -> IUserRepository:
        """Get user repository."""
        factory = self._get_repository_factory()
        return factory.create_user_repository(session)

    def get_chat_repository(self, session: AsyncSession) -> IChatRepository:
        """Get chat repository."""
        factory = self._get_repository_factory()
        return factory.create_chat_repository(session)

    def get_admin_repository(self, session: AsyncSession) -> IAdminRepository:
        """Get admin repository."""
        factory = self._get_repository_factory()
        return factory.create_admin_repository(session)

    def get_message_repository(self, session: AsyncSession) -> IMessageRepository:
        """Get message repository."""
        factory = self._get_repository_factory()
        return factory.create_message_repository(session)

    def get_chat_link_repository(self, session: AsyncSession) -> IChatLinkRepository:
        """Get chat link repository."""
        factory = self._get_repository_factory()
        return factory.create_chat_link_repository(session)

    def get_moderation_service(self, session: AsyncSession) -> ModerationService:
        """Get moderation service."""
        service_registry = self._get_service_registry()
        return service_registry.create_moderation_service(session)

    def get_user_service(self, session: AsyncSession) -> UserService:
        """Get user service."""
        service_registry = self._get_service_registry()
        return service_registry.create_user_service(session)

    def get_spam_service(self, session: AsyncSession) -> SpamService:
        """Get spam service."""
        service_registry = self._get_service_registry()
        return service_registry.create_spam_service(session)


# Global container instance
container = Container()


def get_container() -> Container:
    """Get the global container instance."""
    return container


def setup_container(session_maker: async_sessionmaker[AsyncSession], bot: Bot) -> None:
    """Setup dependency injection container."""
    container.set_session_maker(session_maker)
    container.set_bot(bot)

    # Service registry will handle service registration internally
    service_registry = container._get_service_registry()

    # Register transient services that require a session
    # These are resolved by passing the session explicitly
    service_registry.register_transient(IUserRepository, lambda s: container.get_user_repository(s))
    service_registry.register_transient(IChatRepository, lambda s: container.get_chat_repository(s))
    service_registry.register_transient(IAdminRepository, lambda s: container.get_admin_repository(s))
    service_registry.register_transient(IMessageRepository, lambda s: container.get_message_repository(s))
    service_registry.register_transient(IChatLinkRepository, lambda s: container.get_chat_link_repository(s))

    service_registry.register_transient(ModerationService, lambda s: container.get_moderation_service(s))
    service_registry.register_transient(UserService, lambda s: container.get_user_service(s))
    service_registry.register_transient(SpamService, lambda s: container.get_spam_service(s))
