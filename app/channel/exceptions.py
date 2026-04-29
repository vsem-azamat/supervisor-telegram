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


class TopicSplitError(ChannelPipelineError):
    """Failed to split or enrich content items into individual topics.

    Raised on LLM response parse failures inside ``topic_splitter``. The
    pipeline still degrades gracefully (returns the original items) but
    callers can distinguish topic-split issues from other pipeline errors
    when narrower handling is needed.
    """


class ImagePipelineError(ChannelPipelineError):
    """Recoverable failure in the image pipeline.

    Caller should skip images (``image_urls=[]``) and continue the post
    through review rather than halting the whole content pipeline.
    """
