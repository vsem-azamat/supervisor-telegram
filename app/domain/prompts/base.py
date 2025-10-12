"""Base classes and types for prompt management."""

from dataclasses import dataclass
from enum import Enum


class PromptType(str, Enum):
    """Types of prompts available."""

    MODERATION = "moderation"
    ANALYTICS = "analytics"
    SUPPORT = "support"


@dataclass
class SystemPrompt:
    """System prompt configuration."""

    content: str
    language: str = "ru"
    temperature: float = 0.7
    max_tokens: int = 2000

    def format(self, **kwargs: str) -> str:
        """Format prompt with variables."""
        return self.content.format(**kwargs)
