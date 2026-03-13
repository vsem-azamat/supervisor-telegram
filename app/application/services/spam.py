"""Backward-compatibility shim — moved to app.moderation.spam_service."""

from app.moderation.spam_service import detect_spam

__all__ = ["detect_spam"]
