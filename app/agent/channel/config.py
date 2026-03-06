"""Channel agent configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChannelAgentSettings(BaseSettings):
    """Channel content agent configuration."""

    enabled: bool = Field(default=False, description="Enable channel content agent")
    channel_id: int | str = Field(default=0, description="Target Telegram channel ID or @username")
    fetch_interval_minutes: int = Field(default=60, description="How often to fetch new content")
    max_posts_per_day: int = Field(default=3, description="Maximum posts per day")
    language: str = Field(default="ru", description="Post language (ru, cs, en)")
    require_approval: bool = Field(default=True, description="Require admin approval before posting")

    # RSS sources (comma-separated URLs)
    rss_sources: str = Field(default="", description="Comma-separated RSS feed URLs")

    # LLM settings
    screening_model: str = Field(default="google/gemini-2.0-flash-001", description="Cheap model for screening")
    generation_model: str = Field(default="google/gemini-2.0-flash-001", description="Model for post generation")

    model_config = SettingsConfigDict(
        env_prefix="CHANNEL_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def rss_source_list(self) -> list[str]:
        """Parse comma-separated RSS URLs."""
        if not self.rss_sources:
            return []
        return [url.strip() for url in self.rss_sources.split(",") if url.strip()]
