"""Agent input/output schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession


class EventType(StrEnum):
    REPORT = "report"
    SPAM = "spam"
    TIMEOUT = "timeout"


class ActionType(StrEnum):
    MUTE = "mute"
    BAN = "ban"
    DELETE = "delete"
    WARN = "warn"
    BLACKLIST = "blacklist"
    ESCALATE = "escalate"
    IGNORE = "ignore"


@dataclass
class AgentEvent:
    """Input event for the agent to analyze."""

    event_type: EventType
    chat_id: int
    chat_title: str | None
    message_id: int
    reporter_id: int
    target_user_id: int
    target_username: str | None
    target_display_name: str
    target_message_text: str | None
    context_messages: list[dict[str, str]] = field(default_factory=list)


class ModerationResult(BaseModel):
    """Structured result from the moderation agent."""

    action: Literal["mute", "ban", "delete", "warn", "blacklist", "escalate", "ignore"] = Field(
        description="The moderation action to take"
    )
    reason: str = Field(description="Explanation for the decision in Russian")
    duration_minutes: int | None = Field(default=None, description="Mute duration in minutes (only for mute)")
    warning_text: str | None = Field(default=None, description="Warning message in Russian (only for warn)")
    revoke_messages: bool = Field(default=False, description="Delete all user messages (only for blacklist)")
    suggested_action: str | None = Field(default=None, description="Suggested action when escalating")


@dataclass
class AgentDeps:
    """Dependencies injected into PydanticAI agent at runtime."""

    bot: Bot
    db: AsyncSession
    event: AgentEvent
