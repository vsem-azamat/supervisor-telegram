"""Channel agent configuration."""

from __future__ import annotations

import warnings

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChannelConfig(BaseModel):
    """Per-channel configuration (not settings — instantiated from code or parsed JSON)."""

    channel_id: int | str
    review_chat_id: int | str = 0
    language: str = "ru"
    max_posts_per_day: int = 3
    discovery_query: str = ""
    source_discovery_query: str = ""
    posting_schedule: list[str] = Field(
        default_factory=list,
        description="List of HH:MM times in UTC for scheduled posting (e.g. ['09:00', '18:00'])",
    )

    @field_validator("posting_schedule", mode="before")
    @classmethod
    def parse_posting_schedule(cls, v: object) -> list[str]:
        """Accept comma-separated string or list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v]
        return []


LANGUAGE_NAMES: dict[str, str] = {
    "ru": "Russian",
    "cs": "Czech",
    "en": "English",
}


def language_name(code: str) -> str:
    """Get full language name from code, defaulting to the code itself."""
    return LANGUAGE_NAMES.get(code, code)


class ChannelAgentSettings(BaseSettings):
    """Channel content agent configuration."""

    enabled: bool = Field(default=False, description="Enable channel content agent")

    # --- Legacy single-channel fields (deprecated, kept for backward compat) ---
    channel_id: int | str = Field(default=0, description="[DEPRECATED] Target Telegram channel ID or @username")
    review_chat_id: int | str = Field(
        default=0, description="[DEPRECATED] Private channel/chat for post review with inline buttons"
    )
    fetch_interval_minutes: int = Field(default=60, description="How often to fetch new content")
    max_posts_per_day: int = Field(default=3, description="[DEPRECATED] Maximum posts per day")
    language: str = Field(default="ru", description="[DEPRECATED] Post language (ru, cs, en)")

    # Discovery settings
    discovery_enabled: bool = Field(default=True, description="Enable Perplexity Sonar content discovery")
    discovery_model: str = Field(default="perplexity/sonar", description="Model for content discovery")
    discovery_query: str = Field(
        default="Czech Republic news for international students this week",
        description="[DEPRECATED] Search query for content discovery",
    )

    # Source discovery — agent finds RSS feeds automatically
    source_discovery_enabled: bool = Field(default=True, description="Agent auto-discovers RSS feeds")
    source_discovery_interval_hours: int = Field(default=24, description="How often to search for new feeds")
    source_discovery_query: str = Field(
        default="RSS feeds about Czech Republic education, student life, visas, universities",
        description="[DEPRECATED] Query for finding new RSS feeds",
    )

    # LLM settings
    screening_model: str = Field(
        default="google/gemini-3.1-flash-lite-preview", description="Cheap model for screening"
    )
    generation_model: str = Field(
        default="google/gemini-3.1-flash-lite-preview", description="Model for post generation"
    )
    http_timeout: int = Field(default=30, description="HTTP client timeout in seconds")
    screening_threshold: int = Field(default=5, description="Minimum relevance score (0-10) to pass screening")
    temperature: float = Field(default=0.3, description="LLM temperature for content generation")

    # Embedding settings for semantic dedup
    embedding_model: str = Field(
        default="openai/text-embedding-3-small", description="Embedding model for semantic dedup"
    )
    embedding_dimensions: int = Field(default=768, description="Embedding vector dimensions")
    semantic_dedup_threshold: float = Field(
        default=0.85, description="Cosine similarity threshold to consider items as duplicates (0-1)"
    )

    # Deprecated — sources managed by agent via DB
    rss_sources: str = Field(default="", description="DEPRECATED: use source_discovery_enabled instead")

    # --- Multi-channel configuration ---
    channels: list[ChannelConfig] = Field(
        default_factory=list,
        description="List of per-channel configs (takes priority over legacy single-channel fields)",
    )

    model_config = SettingsConfigDict(
        env_prefix="CHANNEL_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("channels", mode="before")
    @classmethod
    def parse_channels(cls, v: object) -> list[object]:
        """Accept JSON string for channels list from env."""
        if isinstance(v, str):
            if not v.strip():
                return []
            import json

            return json.loads(v)
        if isinstance(v, list):
            return v
        return []

    def get_channels(self) -> list[ChannelConfig]:
        """Return channel configs: explicit list if set, otherwise legacy single-channel fallback.

        If ``channels`` is non-empty it is returned as-is.  Otherwise a single
        ``ChannelConfig`` is constructed from the legacy top-level fields so
        that existing ``.env`` files keep working.
        """
        if self.channels:
            return list(self.channels)

        # Legacy fallback — build one ChannelConfig from top-level fields
        if not self.channel_id:
            return []

        warnings.warn(
            "Using legacy single-channel CHANNEL_* env vars is deprecated. "
            "Migrate to CHANNEL_CHANNELS (JSON list of ChannelConfig).",
            DeprecationWarning,
            stacklevel=2,
        )

        return [
            ChannelConfig(
                channel_id=self.channel_id,
                review_chat_id=self.review_chat_id,
                language=self.language,
                max_posts_per_day=self.max_posts_per_day,
                discovery_query=self.discovery_query,
                source_discovery_query=self.source_discovery_query,
            )
        ]

    @property
    def rss_source_list(self) -> list[str]:
        """Parse comma-separated RSS URLs (deprecated, for initial seeding only)."""
        if not self.rss_sources:
            return []
        return [url.strip() for url in self.rss_sources.split(",") if url.strip()]
