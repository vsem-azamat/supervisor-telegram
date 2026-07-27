"""Core enumerations shared across all layers."""

from enum import StrEnum


class PostStatus(StrEnum):
    """Status of a channel post in the review pipeline."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ReviewDecision(StrEnum):
    """Admin decision on a channel post review."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ModerationAction(StrEnum):
    """An action a proposal can ask for.

    Only removals: everything else a moderator does has its own command and
    happens immediately. Typed rather than a string so an unsupported name
    fails where it is written, not when a human has already pressed confirm.
    """

    BAN = "ban"
    BLACKLIST = "blacklist"


class PendingActionOrigin(StrEnum):
    """Where a proposal came from. Recorded so a ban stays attributable."""

    MCP = "mcp"


class PendingActionStatus(StrEnum):
    """Status of a destructive action awaiting a human press.

    Expiry does nothing. A proposal that runs out of time was made from
    outside and never answered, and silence there has to mean no.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
