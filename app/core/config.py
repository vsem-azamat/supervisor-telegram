"""Application configuration using Pydantic settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from app.agent.channel.config import ChannelAgentSettings


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")
    host: str = Field(default="db", description="Database host")
    port: int = Field(default=5432, description="Database port")
    name: str = Field(..., description="Database name")

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def url(self) -> str:
        """Get async database URL."""
        from sqlalchemy.engine import URL

        return URL.create(
            "postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        ).render_as_string(hide_password=False)

    @property
    def sync_url(self) -> str:
        """Get sync database URL for Alembic."""
        from sqlalchemy.engine import URL

        return URL.create(
            "postgresql",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        ).render_as_string(hide_password=False)


class TelegramSettings(BaseSettings):
    """Telegram bot configuration."""

    token: str = Field(..., description="Bot token from BotFather")

    model_config = SettingsConfigDict(
        env_prefix="BOT_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AdminSettings(BaseSettings):
    """Admin configuration."""

    super_admins: list[int] = Field(..., description="List of super admin user IDs")
    report_chat_id: int | None = Field(default=None, description="Chat ID for reports")

    model_config = SettingsConfigDict(
        env_prefix="ADMIN_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("super_admins", mode="before")
    @classmethod
    def parse_admin_list(cls, v: Any) -> list[int]:
        """Parse comma-separated admin IDs."""
        if isinstance(v, str):
            return [int(admin_id.strip()) for admin_id in v.split(",") if admin_id.strip()]
        if isinstance(v, list):
            return [int(admin_id) for admin_id in v]
        if isinstance(v, int):
            return [v]
        raise ValueError("super_admins must be a comma-separated string, list, or integer")

    @property
    def default_report_chat_id(self) -> int:
        """Get default report chat ID (first super admin)."""
        return self.report_chat_id or self.super_admins[0]


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format")
    file_path: str | None = Field(default="logs/bot.log", description="Log file path")
    max_bytes: int = Field(default=10485760, description="Max log file size in bytes (10MB)")
    backup_count: int = Field(default=5, description="Number of backup log files")

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class OpenRouterSettings(BaseSettings):
    """Shared LLM credentials used by all agents."""

    api_key: str = Field(default="", description="OpenRouter API key")
    base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter API base URL")
    brave_api_key: str = Field(default="", description="Brave Search API key for web search")

    model_config = SettingsConfigDict(
        env_prefix="OPENROUTER_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ModerationSettings(BaseSettings):
    """Moderation agent configuration."""

    model: str = Field(
        default="google/gemini-3.1-flash-lite-preview",
        description="Model for spam/moderation agent in chats",
    )
    escalation_timeout_minutes: int = Field(default=30, description="Minutes before escalation times out")
    default_timeout_action: str = Field(
        default="ignore",
        description="Default action on escalation timeout (mute/ban/delete/warn/blacklist/escalate/ignore)",
    )
    enabled: bool = Field(default=False, description="Whether the moderation agent is enabled")

    @field_validator("default_timeout_action")
    @classmethod
    def validate_timeout_action(cls, v: str) -> str:
        """Validate that the timeout action is a known moderation action."""
        valid = {"mute", "ban", "delete", "warn", "blacklist", "escalate", "ignore"}
        if v not in valid:
            raise ValueError(f"default_timeout_action must be one of {valid}, got '{v}'")
        return v

    model_config = SettingsConfigDict(
        env_prefix="MODERATION_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AssistantSettings(BaseSettings):
    """Settings for the conversational assistant bot."""

    token: str = Field(default="", description="Telegram bot token for assistant bot")
    enabled: bool = Field(default=False, description="Enable assistant bot")
    model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="Model for the assistant bot (channel/chat management)",
    )

    model_config = SettingsConfigDict(
        env_prefix="ASSISTANT_BOT_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class TelethonSettings(BaseSettings):
    """Telethon (Telegram Client API) configuration for userbot features."""

    api_id: int = Field(default=0, description="API ID from https://my.telegram.org")
    api_hash: str = Field(default="", description="API hash from https://my.telegram.org")
    session_name: str = Field(default="moderator_userbot", description="Session file name")
    enabled: bool = Field(default=False, description="Enable Telethon client")
    phone: str | None = Field(default=None, description="Phone number for initial auth")

    model_config = SettingsConfigDict(
        env_prefix="TELETHON_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(BaseSettings):
    """Main application settings."""

    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")
    timezone: str = Field(default="UTC", description="Application timezone")

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    moderation: ModerationSettings = Field(default_factory=ModerationSettings)
    assistant: AssistantSettings = Field(default_factory=AssistantSettings)
    telethon: TelethonSettings = Field(default_factory=TelethonSettings)

    @property
    def channel(self) -> ChannelAgentSettings:
        """Lazily load and cache ChannelAgentSettings singleton."""
        if not hasattr(self, "_channel_settings"):
            from app.agent.channel.config import ChannelAgentSettings

            object.__setattr__(self, "_channel_settings", ChannelAgentSettings())
        return self._channel_settings  # type: ignore[attr-defined]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = AppSettings()
