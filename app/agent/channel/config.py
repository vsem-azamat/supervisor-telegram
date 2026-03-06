"""Channel agent configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChannelAgentSettings(BaseSettings):
    """Channel content agent configuration."""

    enabled: bool = Field(default=False, description="Enable channel content agent")
    channel_id: int | str = Field(default=0, description="Target Telegram channel ID or @username")
    review_chat_id: int | str = Field(default=0, description="Private channel/chat for post review with inline buttons")
    fetch_interval_minutes: int = Field(default=60, description="How often to fetch new content")
    max_posts_per_day: int = Field(default=3, description="Maximum posts per day")
    language: str = Field(default="ru", description="Post language (ru, cs, en)")

    # Discovery settings
    discovery_enabled: bool = Field(default=True, description="Enable Perplexity Sonar content discovery")
    discovery_model: str = Field(default="perplexity/sonar", description="Model for content discovery")
    discovery_query: str = Field(
        default="Czech Republic news for international students this week",
        description="Search query for content discovery",
    )

    # Source discovery — agent finds RSS feeds automatically
    source_discovery_enabled: bool = Field(default=True, description="Agent auto-discovers RSS feeds")
    source_discovery_interval_hours: int = Field(default=24, description="How often to search for new feeds")
    source_discovery_query: str = Field(
        default="RSS feeds about Czech Republic education, student life, visas, universities",
        description="Query for finding new RSS feeds",
    )

    # LLM settings
    screening_model: str = Field(default="google/gemini-2.0-flash-001", description="Cheap model for screening")
    generation_model: str = Field(default="google/gemini-2.0-flash-001", description="Model for post generation")

    # Deprecated — sources managed by agent via DB
    rss_sources: str = Field(default="", description="DEPRECATED: use source_discovery_enabled instead")

    model_config = SettingsConfigDict(
        env_prefix="CHANNEL_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def rss_source_list(self) -> list[str]:
        """Parse comma-separated RSS URLs (deprecated, for initial seeding only)."""
        if not self.rss_sources:
            return []
        return [url.strip() for url in self.rss_sources.split(",") if url.strip()]
