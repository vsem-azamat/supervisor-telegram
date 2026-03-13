"""Backward-compatibility shim — moved to app.moderation.history_service."""

from app.moderation.history_service import merge_chat, merge_user, save_message

__all__ = ["merge_chat", "merge_user", "save_message"]
