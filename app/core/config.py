"""Application configuration using Pydantic settings."""

from typing import Any, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def sync_url(self) -> str:
        """Get sync database URL for Alembic."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class TelegramSettings(BaseSettings):
    """Telegram bot configuration."""

    token: str = Field(..., description="Bot token from BotFather")
    webhook_url: str | None = Field(default=None, description="Webhook URL for production")
    webhook_secret: str | None = Field(default=None, description="Webhook secret token")
    use_webhook: bool = Field(default=False, description="Use webhook instead of polling")

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


class WebAppSettings(BaseSettings):
    """Web application configuration."""

    url: str = Field(default="http://localhost:3000", description="Web app URL")
    api_secret: str = Field(default="", description="API secret for webapp communication")
    api_enabled: bool = Field(default=False, description="Enable the stats/auth HTTP API")
    api_port: int = Field(default=8081, description="Port for the stats/auth HTTP API")
    allowed_emails: list[str] = Field(default_factory=list, description="Emails allowed to request magic links")

    model_config = SettingsConfigDict(
        env_prefix="WEBAPP_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def parse_email_list(cls, v: Any) -> list[str]:
        """Parse comma-separated email list."""
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        if isinstance(v, list):
            return [str(e) for e in v]
        return []

    @model_validator(mode="after")
    def validate_api_secret(self) -> Self:
        """Ensure a real secret is set when the API is enabled."""
        _placeholders = {"", "your-secret-key", "changeme", "secret"}
        if self.api_enabled and self.api_secret in _placeholders:
            raise ValueError("WEBAPP_API_SECRET must be set to a non-placeholder value when WEBAPP_API_ENABLED=true")
        return self


class AgentSettings(BaseSettings):
    """AI agent configuration."""

    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    model: str = Field(default="google/gemini-3.1-pro-preview", description="LLM model to use via OpenRouter")
    temperature: float = Field(default=0.3, description="LLM temperature")
    escalation_timeout_minutes: int = Field(default=30, description="Minutes before escalation times out")
    default_timeout_action: str = Field(default="ignore", description="Default action on escalation timeout")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter API base URL")
    enabled: bool = Field(default=False, description="Whether the agent is enabled")

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
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
    webapp: WebAppSettings = Field(default_factory=WebAppSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    telethon: TelethonSettings = Field(default_factory=TelethonSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = AppSettings()
