"""
Centralized prompt management for AI agents.

All system prompts, tool descriptions, and prompt templates are defined here.
"""

from app.domain.prompts.system import (
    DEFAULT_SYSTEM_PROMPT,
    MODERATION_SYSTEM_PROMPT,
    get_system_prompt,
)

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "MODERATION_SYSTEM_PROMPT",
    "get_system_prompt",
]
