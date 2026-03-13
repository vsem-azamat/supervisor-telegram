"""Backward-compatibility shim — moved to app.moderation.escalation."""

from app.moderation.escalation import EscalationService, _timeout_tasks

__all__ = ["EscalationService", "_timeout_tasks"]
