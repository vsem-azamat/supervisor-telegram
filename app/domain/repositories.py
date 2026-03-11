"""Repository interfaces (ports) for the domain layer."""

from abc import ABC, abstractmethod
from typing import Any

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
    async def has_previous_messages(self, chat_id: int, user_id: int) -> bool:
        """Check if user has any previous messages in this chat."""
        pass

    async def is_first_message(self, chat_id: int, user_id: int) -> bool:
        """Check if this is the user's first message in the chat."""
        return not await self.has_previous_messages(chat_id, user_id)

    @abstractmethod
    async def is_similar_spam_message(self, message: str) -> bool:
        """Check if similar spam message exists."""
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
