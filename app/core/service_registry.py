"""Service registry for managing application services."""

from typing import Any, TypeVar

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.moderation_service import ModerationService
from app.application.services.spam import SpamService
from app.application.services.user_service import UserService
from app.core.repository_factory import RepositoryFactory

T = TypeVar("T")


class ServiceRegistry:
    """Registry for managing application services."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession], bot: Bot | None = None) -> None:
        self.session_maker = session_maker
        self.bot = bot
        self._services: dict[type[Any], Any] = {}
        self._singletons: dict[type[Any], Any] = {}
        self.repository_factory = RepositoryFactory()

    def register_singleton(self, interface: type[T], instance: T) -> None:
        """Register a singleton service."""
        self._singletons[interface] = instance

    def register_transient(self, interface: type[T], factory: Any) -> None:
        """Register a transient service with factory."""
        self._services[interface] = factory

    def get(self, interface: type[T]) -> T:
        """Get service instance."""
        # Check singletons first
        if interface in self._singletons:
            return self._singletons[interface]  # type: ignore

        # Check transient services
        if interface in self._services:
            factory = self._services[interface]
            return factory()  # type: ignore

        raise ValueError(f"Service {interface} not registered")

    def create_moderation_service(self, session: AsyncSession) -> ModerationService:
        """Create moderation service with dependencies."""
        if not self.bot:
            raise ValueError("Bot instance not set in ServiceRegistry")

        chat_repo = self.repository_factory.create_chat_repository(session)
        user_repo = self.repository_factory.create_user_repository(session)
        message_repo = self.repository_factory.create_message_repository(session)
        spam_service = self.create_spam_service(session)

        return ModerationService(
            bot=self.bot,
            chat_repository=chat_repo,
            message_repository=message_repo,
            user_repository=user_repo,
            spam_service=spam_service,
        )

    def create_user_service(self, session: AsyncSession) -> UserService:
        """Create user service with dependencies."""
        user_repo = self.repository_factory.create_user_repository(session)
        return UserService(user_repo)

    def create_spam_service(self, session: AsyncSession) -> SpamService:
        """Create spam service with dependencies."""
        message_repo = self.repository_factory.create_message_repository(session)
        return SpamService(message_repo)
