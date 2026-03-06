"""Assistant bot configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AssistantSettings(BaseSettings):
    """Settings for the conversational assistant bot."""

    token: str = Field(default="", description="Telegram bot token for assistant bot")
    enabled: bool = Field(default=False, description="Enable assistant bot")

    model_config = SettingsConfigDict(
        env_prefix="ASSISTANT_BOT_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
