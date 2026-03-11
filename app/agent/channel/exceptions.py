"""Domain-specific exceptions for the channel content pipeline."""


class ChannelPipelineError(Exception):
    """Base exception for channel pipeline errors."""


class SourceFetchError(ChannelPipelineError):
    """Failed to fetch content from a source (RSS, web search)."""


class ScreeningError(ChannelPipelineError):
    """Failed during content screening/relevance check."""


class GenerationError(ChannelPipelineError):
    """Failed to generate a post from content items."""


class PublishError(ChannelPipelineError):
    """Failed to publish or send a post for review."""


class EmbeddingError(ChannelPipelineError):
    """Failed to compute or store embeddings."""


class DiscoveryError(ChannelPipelineError):
    """Failed during content or source discovery."""
