"""Core enumerations shared across all layers."""

from enum import StrEnum


class PostStatus(StrEnum):
    """Status of a channel post in the review pipeline."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class EscalationStatus(StrEnum):
    """Status of an agent escalation."""

    PENDING = "pending"
    RESOLVED = "resolved"
    TIMEOUT = "timeout"


class ReviewDecision(StrEnum):
    """Admin decision on a channel post review."""

    APPROVED = "approved"
    REJECTED = "rejected"


class PendingActionStatus(StrEnum):
    """Status of a destructive action awaiting a human press.

    Note EXPIRED against EscalationStatus.TIMEOUT: an escalation that runs out
    of time carries out its default action, because the bot already judged
    something wrong and was only asking for a second opinion. A pending action
    that runs out of time does nothing at all — it was proposed from outside,
    and silence there has to mean no.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
