"""Semantic deduplication using pgvector embeddings.

Provides two main functions:
- filter_semantic_duplicates: removes items similar to recent posts (cross-source dedup)
- store_post_embedding: saves embedding after post creation for future dedup
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.agent.channel.embeddings import DEFAULT_EMBEDDING_DIMS, DEFAULT_EMBEDDING_MODEL, get_embeddings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.semantic_dedup")


async def filter_semantic_duplicates(
    items: list[ContentItem],
    *,
    channel_id: str,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMS,
    threshold: float = 0.85,
    lookback_days: int = 7,
) -> list[ContentItem]:
    """Filter out items semantically similar to recent posts.

    For each candidate item, computes its title embedding and checks
    cosine similarity against recent channel_posts embeddings.
    Items with similarity >= threshold are considered duplicates and removed.

    Returns the filtered list of unique items.
    """
    if not items:
        return []

    # Build texts for embedding (title + first 100 chars of body)
    texts = [f"{item.title} {item.body[:100]}" for item in items]

    try:
        embeddings = await get_embeddings(texts, api_key=api_key, model=model, dimensions=dimensions)
    except Exception:
        logger.exception("embedding_api_error_skipping_semantic_dedup")
        return items  # Graceful degradation — skip semantic dedup on API failure

    unique_items: list[ContentItem] = []

    for item, embedding in zip(items, embeddings, strict=True):
        is_dup = await _is_similar_to_recent(
            embedding=embedding,
            channel_id=channel_id,
            session_maker=session_maker,
            threshold=threshold,
            lookback_days=lookback_days,
        )
        if is_dup:
            logger.info(
                "semantic_duplicate_filtered",
                title=item.title[:60],
                channel_id=channel_id,
            )
        else:
            unique_items.append(item)

    filtered_count = len(items) - len(unique_items)
    if filtered_count:
        logger.info(
            "semantic_dedup_done",
            total=len(items),
            filtered=filtered_count,
            remaining=len(unique_items),
        )

    return unique_items


async def _is_similar_to_recent(
    *,
    embedding: list[float],
    channel_id: str,
    session_maker: async_sessionmaker[AsyncSession],
    threshold: float,
    lookback_days: int,
) -> bool:
    """Check if an embedding is similar to any recent post in the channel."""
    # pgvector cosine distance: 1 - cosine_similarity
    # So distance < (1 - threshold) means similarity > threshold
    max_distance = 1.0 - threshold

    raw_query = text("""
        SELECT 1 FROM channel_posts
        WHERE channel_id = :channel_id
          AND embedding IS NOT NULL
          AND created_at > NOW() - make_interval(days => :days)
          AND (embedding <=> cast(:embedding as vector)) < :max_distance
        LIMIT 1
    """)

    async with session_maker() as session:
        result = await session.execute(
            raw_query,
            {
                "channel_id": channel_id,
                "days": lookback_days,
                "max_distance": max_distance,
                "embedding": str(embedding),
            },
        )
        return result.scalar_one_or_none() is not None


async def store_post_embedding(
    *,
    post_id: int,
    text_for_embedding: str,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = DEFAULT_EMBEDDING_MODEL,
    dimensions: int = DEFAULT_EMBEDDING_DIMS,
) -> None:
    """Compute and store embedding for a channel post."""
    from app.infrastructure.db.models import ChannelPost

    try:
        embeddings = await get_embeddings([text_for_embedding], api_key=api_key, model=model, dimensions=dimensions)
        embedding = embeddings[0]

        async with session_maker() as session:
            result = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post: ChannelPost | None = result.scalar_one_or_none()
            if post:
                post.embedding = embedding
                post.embedding_model = model
                await session.commit()
                logger.info("embedding_stored", post_id=post_id, model=model)
    except Exception:
        logger.exception("store_embedding_error", post_id=post_id)
        # Non-fatal — post is already saved, embedding is optional
