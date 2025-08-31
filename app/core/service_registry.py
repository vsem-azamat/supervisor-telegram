"""Service registry for managing application services."""

from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.services.agent_service import AgentService
from app.core.logging import BotLogger
from app.core.repository_factory import RepositoryFactory

T = TypeVar("T")


class ServiceRegistry:
    """Registry for managing application services."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self.session_maker = session_maker
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

    def create_agent_service(self) -> AgentService:
        """Create agent service with dependencies."""
        session = self.session_maker()

        agent_repo = self.repository_factory.get_agent_repository()
        chat_repo = self.repository_factory.create_chat_repository(session)
        user_repo = self.repository_factory.create_user_repository(session)
        logger = BotLogger("AgentService")

        return AgentService(agent_repo, chat_repo, user_repo, logger)
