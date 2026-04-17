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


DEFAULT_DISCOVERY_QUERY = "Czech Republic news for international students this week"
DEFAULT_SOURCE_DISCOVERY_QUERY = "RSS feeds about Czech Republic education, student life, visas, universities"
DEFAULT_BRAVE_DISCOVERY_QUERY = "Czech Republic students news this week"


class ChannelAgentSettings(BaseSettings):
    """Channel content agent configuration."""

    enabled: bool = Field(default=False, description="Enable channel content agent")
    fetch_interval_minutes: int = Field(default=60, description="How often to fetch new content")

    # Discovery settings
    discovery_enabled: bool = Field(default=True, description="Enable Perplexity Sonar content discovery")
    discovery_model: str = Field(default="perplexity/sonar", description="Model for content discovery")

    # Source discovery — agent finds RSS feeds automatically
    source_discovery_enabled: bool = Field(default=True, description="Agent auto-discovers RSS feeds")
    source_discovery_interval_hours: int = Field(default=24, description="How often to search for new feeds")

    # LLM settings
    screening_model: str = Field(
        default="google/gemini-3.1-flash-lite-preview", description="Cheap model for screening"
    )
    generation_model: str = Field(
        default="google/gemini-3.1-flash-lite-preview", description="Model for post generation"
    )
    vision_model: str = Field(
        default="google/gemini-2.5-flash",
        description="Multimodal model for scoring candidate images (OpenRouter slug)",
    )
    image_phash_lookback_posts: int = Field(
        default=30,
        description="How many recent approved posts to compare pHash against for dedup",
    )
    image_phash_threshold: int = Field(
        default=10,
        description="Hamming distance threshold for pHash duplicate detection (0-64)",
    )
    http_timeout: int = Field(default=30, description="HTTP client timeout in seconds")
    screening_threshold: int = Field(default=5, description="Minimum relevance score (0-10) to pass screening")
    temperature: float = Field(default=0.3, description="LLM temperature for content generation")
    critic_enabled: bool = Field(
        default=False,
        description="Master kill-switch for the post critic polish pass",
    )
    critic_model: str = Field(
        default="anthropic/claude-sonnet-4-6",
        description="Model used by the critic agent",
    )

    # Brave Search — complementary to Perplexity for URL-based factual search
    brave_discovery_enabled: bool = Field(
        default=False, description="Enable Brave Web Search as additional discovery source"
    )

    # Embedding settings for semantic dedup
    # NOTE: embedding dimension (768) is a schema constant in embeddings.py — changing it requires a DB migration
    embedding_model: str = Field(
        default="openai/text-embedding-3-small", description="Embedding model for semantic dedup"
    )
    semantic_dedup_threshold: float = Field(
        default=0.85, description="Cosine similarity threshold to consider items as duplicates (0-1)"
    )
    dedup_lookback_days: int = Field(
        default=7, description="How many days back to compare new items against published/reviewed posts"
    )
    dedup_query_snippet_chars: int = Field(
        default=200,
        description="Max chars sent to embedding API when querying nearest posts (inputs longer than this are clipped)",
    )
    backfill_batch_size: int = Field(default=32, description="Batch size for scripts/backfill_embeddings.py")
    # NOTE: `body_chars` (default 100) that truncates item body for the embedding
    # input lives in app/channel/semantic_dedup.py::DEFAULT_EMBED_BODY_CHARS.
    # It is a schema-like constant — changing it invalidates every stored vector
    # and requires re-running scripts/backfill_embeddings.py.

    model_config = SettingsConfigDict(
        env_prefix="CHANNEL_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
