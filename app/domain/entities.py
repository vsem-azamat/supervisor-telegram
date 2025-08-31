"""Domain entities for the moderation bot."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class UserEntity:
    """User domain entity."""

    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_verified: bool = True
    is_blocked: bool = False
    created_at: datetime | None = None
    modified_at: datetime | None = None

    @property
    def display_name(self) -> str:
        """Get user's display name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return f"User {self.id}"

    def block(self) -> None:
        """Block user (add to blacklist)."""
        self.is_blocked = True

    def unblock(self) -> None:
        """Unblock user (remove from blacklist)."""
        self.is_blocked = False


@dataclass
class ChatEntity:
    """Chat domain entity."""

    id: int
    title: str | None = None
    is_forum: bool = False
    welcome_message: str | None = None
    welcome_delete_time: int = 60
    is_welcome_enabled: bool = False
    is_captcha_enabled: bool = False
    auto_delete_join_leave: bool = False
    created_at: datetime | None = None
    modified_at: datetime | None = None

    def enable_welcome(self, message: str | None = None) -> None:
        """Enable welcome message for new members."""
        self.is_welcome_enabled = True
        if message:
            self.welcome_message = message

    def disable_welcome(self) -> None:
        """Disable welcome message."""
        self.is_welcome_enabled = False

    def set_welcome_delete_time(self, seconds: int) -> None:
        """Set auto-delete time for welcome messages."""
        if seconds <= 0:
            raise ValueError("Delete time must be positive")
        self.welcome_delete_time = seconds

    def enable_captcha(self) -> None:
        """Enable captcha for new members."""
        self.is_captcha_enabled = True

    def disable_captcha(self) -> None:
        """Disable captcha for new members."""
        self.is_captcha_enabled = False

    def enable_auto_delete_join_leave(self) -> None:
        """Enable auto-deletion of join/leave messages."""
        self.auto_delete_join_leave = True

    def disable_auto_delete_join_leave(self) -> None:
        """Disable auto-deletion of join/leave messages."""
        self.auto_delete_join_leave = False

    def toggle_auto_delete_join_leave(self) -> None:
        """Toggle auto-deletion of join/leave messages."""
        self.auto_delete_join_leave = not self.auto_delete_join_leave


@dataclass
class AdminEntity:
    """Admin domain entity."""

    id: int
    is_active: bool = True

    def activate(self) -> None:
        """Activate admin status."""
        self.is_active = True

    def deactivate(self) -> None:
        """Deactivate admin status."""
        self.is_active = False


@dataclass
class MessageEntity:
    """Message domain entity."""

    id: int | None
    chat_id: int
    user_id: int
    message_id: int
    content: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: datetime | None = None
    is_spam: bool = False

    def mark_as_spam(self) -> None:
        """Mark message as spam."""
        self.is_spam = True

    def unmark_as_spam(self) -> None:
        """Remove spam marking."""
        self.is_spam = False


@dataclass
class ChatLinkEntity:
    """Chat link domain entity."""

    id: int | None
    text: str
    link: str
    priority: int = 0

    def update_priority(self, priority: int) -> None:
        """Update link priority."""
        self.priority = priority
