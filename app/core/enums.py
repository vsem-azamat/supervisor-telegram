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
