"""Backward-compatibility shim — moved to app.moderation.user_service."""

from app.moderation.user_service import UserService

__all__ = ["UserService"]
