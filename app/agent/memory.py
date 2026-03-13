"""Backward-compatibility shim — moved to app.moderation.memory."""

from app.moderation.memory import AgentMemory, UserRiskProfile

__all__ = ["AgentMemory", "UserRiskProfile"]
