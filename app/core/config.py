"""Application configuration using Pydantic settings."""

from typing import Any

from pydantic import Field, field_validator
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
    api_secret: str = Field(default="your-secret-key", description="API secret for webapp communication")

    model_config = SettingsConfigDict(
        env_prefix="WEBAPP_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AIAgentSettings(BaseSettings):
    """AI Agent configuration."""

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openai_base_url: str = Field(default="", description="Custom OpenAI base URL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter base URL")

    def has_openai_key(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.openai_api_key and self.openai_api_key != "your_openai_api_key_here")

    def has_openrouter_key(self) -> bool:
        """Check if OpenRouter API key is configured."""
        return bool(self.openrouter_api_key and self.openrouter_api_key != "your_openrouter_api_key_here")

    model_config = SettingsConfigDict(
        env_prefix="",  # No prefix, use direct env var names
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class McpSettings(BaseSettings):
    """MCP Server configuration."""

    url: str = Field(default="http://mcp-server:8000/sse", description="MCP server SSE URL")

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
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
    ai_agent: AIAgentSettings = Field(default_factory=AIAgentSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance
settings = AppSettings()
