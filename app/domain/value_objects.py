"""Domain value objects for the moderation bot."""

from dataclasses import dataclass
from enum import Enum, StrEnum


class PostStatus(StrEnum):
    """Status of a channel post in the review pipeline."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    APPROVED = "approved"
    REJECTED = "rejected"


class EscalationStatus(StrEnum):
    """Status of an agent escalation."""

    PENDING = "pending"
    RESOLVED = "resolved"
    TIMEOUT = "timeout"


class ReviewDecision(StrEnum):
    """Admin decision on a channel post review."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ModerationAction(Enum):
    """Types of moderation actions."""

    MUTE = "mute"
    UNMUTE = "unmute"
    BAN = "ban"
    UNBAN = "unban"
    KICK = "kick"
    WARN = "warn"
    DELETE_MESSAGE = "delete_message"


class ChatType(Enum):
    """Types of chats."""

    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


@dataclass(frozen=True)
class UserId:
    """User ID value object."""

    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError("User ID must be positive")


@dataclass(frozen=True)
class ChatId:
    """Chat ID value object."""

    value: int

    def __post_init__(self):
        if self.value == 0:
            raise ValueError("Chat ID cannot be zero")


@dataclass(frozen=True)
class MessageId:
    """Message ID value object."""

    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError("Message ID must be positive")


# Constants
MAX_MUTE_DURATION_MINUTES = 525600  # 1 year in minutes


@dataclass(frozen=True)
class MuteDuration:
    """Mute duration value object."""

    minutes: int

    def __post_init__(self):
        if self.minutes <= 0:
            raise ValueError("Mute duration must be positive")
        if self.minutes > MAX_MUTE_DURATION_MINUTES:
            raise ValueError("Mute duration cannot exceed 1 year")

    @property
    def seconds(self) -> int:
        """Get duration in seconds."""
        return self.minutes * 60


@dataclass(frozen=True)
class WelcomeSettings:
    """Welcome message settings value object."""

    enabled: bool = False
    message: str | None = None
    delete_after_seconds: int = 60
    captcha_enabled: bool = False

    def __post_init__(self):
        if self.delete_after_seconds <= 0:
            raise ValueError("Delete time must be positive")
        if self.enabled and not self.message:
            raise ValueError("Welcome message text is required when enabled")


@dataclass(frozen=True)
class UserProfile:
    """User profile value object."""

    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    @property
    def display_name(self) -> str:
        """Get user's display name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return "Unknown User"

    @property
    def mention(self) -> str:
        """Get user mention for Telegram."""
        if self.username:
            return f"@{self.username}"
        return self.display_name
