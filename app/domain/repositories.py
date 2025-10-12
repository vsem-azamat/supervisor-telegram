"""Repository interfaces (ports) for the domain layer."""

from abc import ABC, abstractmethod
from typing import Any

from app.domain.agent import AgentSession, ModelProvider, OpenRouterModel
from app.domain.entities import (
    AdminEntity,
    ChatEntity,
    ChatLinkEntity,
    MessageEntity,
    UserEntity,
)


class IUserRepository(ABC):
    """User repository interface."""

    @abstractmethod
    async def get_by_id(self, user_id: int) -> UserEntity | None:
        """Get user by ID."""
        pass

    @abstractmethod
    async def save(self, user: UserEntity) -> UserEntity:
        """Save user."""
        pass

    @abstractmethod
    async def get_blocked_users(self) -> list[UserEntity]:
        """Get all blocked users."""
        pass

    @abstractmethod
    async def find_blocked_user(self, identifier: str) -> UserEntity | None:
        """Find blocked user by username (without @) or user_id."""
        pass

    @abstractmethod
    async def exists(self, user_id: int) -> bool:
        """Check if user exists."""
        pass

    @abstractmethod
    async def add_to_blacklist(self, user_id: int) -> None:
        """Mark user as blocked/blacklisted."""
        pass

    @abstractmethod
    async def remove_from_blacklist(self, user_id: int) -> None:
        """Remove user from blacklist."""
        pass


class IChatRepository(ABC):
    """Chat repository interface."""

    @abstractmethod
    async def get_by_id(self, chat_id: int) -> ChatEntity | None:
        """Get chat by ID."""
        pass

    @abstractmethod
    async def save(self, chat: ChatEntity) -> ChatEntity:
        """Save chat."""
        pass

    @abstractmethod
    async def get_all(self) -> list[ChatEntity]:
        """Get all chats."""
        pass

    @abstractmethod
    async def exists(self, chat_id: int) -> bool:
        """Check if chat exists."""
        pass


class IAdminRepository(ABC):
    """Admin repository interface."""

    @abstractmethod
    async def get_by_id(self, admin_id: int) -> AdminEntity | None:
        """Get admin by ID."""
        pass

    @abstractmethod
    async def save(self, admin: AdminEntity) -> AdminEntity:
        """Save admin."""
        pass

    @abstractmethod
    async def delete(self, admin_id: int) -> None:
        """Delete admin."""
        pass

    @abstractmethod
    async def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        pass

    @abstractmethod
    async def get_all_active(self) -> list[AdminEntity]:
        """Get all active admins."""
        pass


class IMessageRepository(ABC):
    """Message repository interface."""

    @abstractmethod
    async def save(self, message: MessageEntity) -> MessageEntity:
        """Save message."""
        pass

    @abstractmethod
    async def get_user_messages(self, user_id: int, chat_id: int | None = None) -> list[MessageEntity]:
        """Get messages by user."""
        pass

    @abstractmethod
    async def get_spam_messages(self, limit: int | None = None) -> list[MessageEntity]:
        """Get spam messages."""
        pass

    @abstractmethod
    async def delete_user_messages(self, user_id: int, chat_id: int | None = None) -> int:
        """Delete user messages and return count."""
        pass

    @abstractmethod
    async def add_message(
        self, chat_id: int, user_id: int, message_id: int, message: str | None, message_info: dict[str, Any]
    ) -> None:
        """Add message (legacy method)."""
        pass

    @abstractmethod
    async def is_first_message(self, chat_id: int, user_id: int) -> bool:
        """Check if this is the user's first message in chat."""
        pass

    @abstractmethod
    async def is_similar_spam_message(self, message: str) -> bool:
        """Check if similar spam message exists."""
        pass

    @abstractmethod
    async def count_user_chats(self, user_id: int) -> int:
        """Count distinct chats user has messages in."""
        pass

    @abstractmethod
    async def count_user_messages(self, user_id: int) -> int:
        """Count total messages sent by user."""
        pass

    @abstractmethod
    async def label_spam(self, chat_id: int, message_id: int) -> None:
        """Mark specific message as spam."""
        pass

    @abstractmethod
    async def get_message_count_24h(self, chat_id: int) -> int:
        """Get message count in last 24 hours."""
        pass

    @abstractmethod
    async def get_active_users_24h(self, chat_id: int) -> int:
        """Get active user count in last 24 hours."""
        pass

    @abstractmethod
    async def get_last_activity(self, chat_id: int) -> Any:
        """Get last activity timestamp."""
        pass


class IChatLinkRepository(ABC):
    """Chat link repository interface."""

    @abstractmethod
    async def get_all(self) -> list[ChatLinkEntity]:
        """Get all chat links ordered by priority."""
        pass

    @abstractmethod
    async def save(self, chat_link: ChatLinkEntity) -> ChatLinkEntity:
        """Save chat link."""
        pass

    @abstractmethod
    async def delete(self, link_id: int) -> None:
        """Delete chat link."""
        pass


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
