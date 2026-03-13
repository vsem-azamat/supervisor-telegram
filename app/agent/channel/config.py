"""Channel agent configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    fetch_interval_minutes: int = Field(default=60, description="How often to fetch new content")

    # Discovery settings
    discovery_enabled: bool = Field(default=True, description="Enable Perplexity Sonar content discovery")
    discovery_model: str = Field(default="perplexity/sonar", description="Model for content discovery")
    discovery_query: str = Field(
        default="Czech Republic news for international students this week",
        description="Default discovery query (overridden per-channel via DB)",
    )

    # Source discovery — agent finds RSS feeds automatically
    source_discovery_enabled: bool = Field(default=True, description="Agent auto-discovers RSS feeds")
    source_discovery_interval_hours: int = Field(default=24, description="How often to search for new feeds")
    source_discovery_query: str = Field(
        default="RSS feeds about Czech Republic education, student life, visas, universities",
        description="Default query for finding new RSS feeds",
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

    # Brave Search — complementary to Perplexity for URL-based factual search
    brave_discovery_enabled: bool = Field(
        default=False, description="Enable Brave Web Search as additional discovery source"
    )
    brave_discovery_query: str = Field(
        default="Czech Republic students news this week",
        description="Brave Search query for content discovery",
    )

    # Embedding settings for semantic dedup
    # NOTE: embedding dimension (768) is a schema constant in embeddings.py — changing it requires a DB migration
    embedding_model: str = Field(
        default="openai/text-embedding-3-small", description="Embedding model for semantic dedup"
    )
    semantic_dedup_threshold: float = Field(
        default=0.85, description="Cosine similarity threshold to consider items as duplicates (0-1)"
    )

    model_config = SettingsConfigDict(
        env_prefix="CHANNEL_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
