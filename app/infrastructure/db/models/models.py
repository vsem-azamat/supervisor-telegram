import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    state: Mapped[bool] = mapped_column(Boolean, default=True)

    def __init__(self, id: int, state: bool = True) -> None:
        self.id = id
        self.state = state

    def activate(self) -> None:
        """Activate admin status"""
        self.state = True

    def deactivate(self) -> None:
        """Deactivate admin status"""
        self.state = False

    @property
    def is_active(self) -> bool:
        """Check if admin is active"""
        return self.state


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    is_forum: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_message: Mapped[str | None] = mapped_column(String, nullable=True)
    time_delete: Mapped[int] = mapped_column(Integer, default=60)
    is_welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_delete_join_leave: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    modified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now
    )

    def __init__(
        self,
        id: int,
        title: str | None = None,
        is_forum: bool = False,
        welcome_message: str | None = None,
        time_delete: int = 60,
        is_welcome_enabled: bool = False,
        is_captcha_enabled: bool = False,
        auto_delete_join_leave: bool = False,
    ) -> None:
        self.id = id
        self.title = title
        self.is_forum = is_forum
        self.welcome_message = welcome_message
        self.time_delete = time_delete
        self.is_welcome_enabled = is_welcome_enabled
        self.is_captcha_enabled = is_captcha_enabled
        self.auto_delete_join_leave = auto_delete_join_leave

    def enable_welcome(self, message: str | None = None) -> None:
        """Enable welcome message for new members"""
        self.is_welcome_enabled = True
        if message:
            self.welcome_message = message

    def disable_welcome(self) -> None:
        """Disable welcome message"""
        self.is_welcome_enabled = False

    def set_welcome_message(self, message: str) -> None:
        """Set welcome message text"""
        self.welcome_message = message

    def set_welcome_delete_time(self, seconds: int) -> None:
        """Set auto-delete time for welcome messages"""
        if seconds > 0:
            self.time_delete = seconds
        else:
            raise ValueError("Delete time must be positive")

    def enable_captcha(self) -> None:
        """Enable captcha for new members"""
        self.is_captcha_enabled = True

    def disable_captcha(self) -> None:
        """Disable captcha"""
        self.is_captcha_enabled = False

    def enable_auto_delete_join_leave(self) -> None:
        """Enable auto-deletion of join/leave messages"""
        self.auto_delete_join_leave = True

    def disable_auto_delete_join_leave(self) -> None:
        """Disable auto-deletion of join/leave messages"""
        self.auto_delete_join_leave = False


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    verify: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    modified_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now
    )

    def __init__(
        self,
        id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        verify: bool = True,
        blocked: bool = False,
    ) -> None:
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.verify = verify
        self.blocked = blocked

    def block(self) -> None:
        """Block user (add to blacklist)"""
        self.blocked = True

    def unblock(self) -> None:
        """Unblock user (remove from blacklist)"""
        self.blocked = False

    def verify_user(self) -> None:
        """Mark user as verified"""
        self.verify = True

    def unverify_user(self) -> None:
        """Mark user as unverified"""
        self.verify = False

    @property
    def is_blocked(self) -> bool:
        """Check if user is blocked"""
        return self.blocked

    @property
    def is_verified(self) -> bool:
        """Check if user is verified"""
        return self.verify

    @property
    def display_name(self) -> str:
        """Get user's display name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return f"User {self.id}"

    def update_profile(
        self, username: str | None = None, first_name: str | None = None, last_name: str | None = None
    ) -> None:
        """Update user profile information"""
        if username is not None:
            self.username = username
        if first_name is not None:
            self.first_name = first_name
        if last_name is not None:
            self.last_name = last_name


class ChatLink(Base):
    __tablename__ = "chat_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String, unique=True)
    link: Mapped[str] = mapped_column(String, unique=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    def __init__(self, text: str, link: str, priority: int = 0) -> None:
        self.text = text
        self.link = link
        self.priority = priority

    def update_priority(self, priority: int) -> None:
        """Update link priority"""
        self.priority = priority

    def update_text(self, text: str) -> None:
        """Update link display text"""
        self.text = text

    def update_link(self, link: str) -> None:
        """Update link URL"""
        self.link = link


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    message_info: Mapped[dict[str, Any]] = mapped_column(JSON)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    spam: Mapped[bool] = mapped_column(Boolean, default=False)

    def __init__(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        message: str | None = None,
        message_info: dict[str, Any] | None = None,
        spam: bool = False,
    ) -> None:
        self.chat_id = chat_id
        self.user_id = user_id
        self.message_id = message_id
        self.message = message
        self.message_info = message_info or {}
        self.spam = spam

    def mark_as_spam(self) -> None:
        """Mark message as spam"""
        self.spam = True

    def unmark_as_spam(self) -> None:
        """Remove spam marking"""
        self.spam = False

    @property
    def is_spam(self) -> bool:
        """Check if message is marked as spam"""
        return self.spam
