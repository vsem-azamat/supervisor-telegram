"""Semantic deduplication using pgvector embeddings.

Provides two main functions:
- filter_semantic_duplicates: removes items similar to recent posts (cross-source dedup)
- store_post_embedding: saves embedding after post creation for future dedup
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, text

from app.agent.channel.embeddings import EMBEDDING_MODEL, get_embeddings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.semantic_dedup")


def format_vector(embedding: list[float]) -> str:
    """Format embedding as pgvector-compatible string with explicit precision."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


async def filter_semantic_duplicates(
    items: list[ContentItem],
    *,
    channel_id: str,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = EMBEDDING_MODEL,
    threshold: float = 0.85,
    lookback_days: int = 7,
) -> list[ContentItem]:
    """Filter out items semantically similar to recent posts.

    Computes embeddings for all items in a single batch, then checks
    cosine similarity against recent channel_posts in a single SQL query.
    Items with similarity >= threshold are considered duplicates and removed.

    Returns the filtered list of unique items.
    """
    if not items:
        return []

    # Build texts for embedding (title + first 100 chars of body)
    texts = [f"{item.title} {item.body[:100]}" for item in items]

    try:
        embeddings = await get_embeddings(texts, api_key=api_key, model=model)
    except Exception:
        logger.warning("embedding_api_error_skipping_semantic_dedup", exc_info=True)
        return items  # Graceful degradation — skip semantic dedup on API failure

    # Batch similarity check — single query for all candidates
    duplicate_indices = await _find_similar_indices(
        embeddings=embeddings,
        channel_id=channel_id,
        session_maker=session_maker,
        threshold=threshold,
        lookback_days=lookback_days,
    )

    unique_items: list[ContentItem] = []
    for i, item in enumerate(items):
        if i in duplicate_indices:
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


async def _find_similar_indices(
    *,
    embeddings: list[list[float]],
    channel_id: str,
    session_maker: async_sessionmaker[AsyncSession],
    threshold: float,
    lookback_days: int,
) -> set[int]:
    """Check all embeddings against recent posts in a single batched query.

    Returns set of indices (into the embeddings list) that are duplicates.
    """
    if not embeddings:
        return set()

    max_distance = 1.0 - threshold

    # Build a VALUES list for all candidate embeddings
    # Uses unnest with array of vectors to batch all comparisons
    values_parts: list[str] = []
    params: dict[str, object] = {
        "channel_id": channel_id,
        "days": lookback_days,
        "max_distance": max_distance,
    }
    for i, emb in enumerate(embeddings):
        param_name = f"emb_{i}"
        values_parts.append(f"({i}, cast(:{param_name} as vector))")
        params[param_name] = format_vector(emb)

    values_sql = ", ".join(values_parts)

    query = text(f"""
        SELECT DISTINCT c.idx
        FROM (VALUES {values_sql}) AS c(idx, vec)
        WHERE EXISTS (
            SELECT 1 FROM channel_posts cp
            WHERE cp.channel_id = :channel_id
              AND cp.embedding IS NOT NULL
              AND cp.created_at > NOW() - make_interval(days => :days)
              AND (cp.embedding <=> c.vec) < :max_distance
        )
    """)  # noqa: S608

    async with session_maker() as session:
        result = await session.execute(query, params)
        return {row[0] for row in result.fetchall()}


async def find_nearest_posts(
    text_for_embedding: str,
    *,
    channel_id: str,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = EMBEDDING_MODEL,
    limit: int = 5,
    lookback_days: int = 7,
) -> list[tuple[str, float]]:
    """Find posts most similar to the given text.

    Returns list of (title, similarity_score) tuples, ordered by similarity desc.
    """
    embeddings = await get_embeddings([text_for_embedding[:200]], api_key=api_key, model=model)
    vec_str = format_vector(embeddings[0])

    query = text("""
        SELECT cp.title, 1.0 - (cp.embedding <=> cast(:vec as vector)) as similarity
        FROM channel_posts cp
        WHERE cp.channel_id = :channel_id
          AND cp.embedding IS NOT NULL
          AND cp.created_at > NOW() - make_interval(days => :days)
        ORDER BY cp.embedding <=> cast(:vec as vector)
        LIMIT :lim
    """)  # noqa: S608

    async with session_maker() as session:
        result = await session.execute(
            query, {"channel_id": channel_id, "vec": vec_str, "days": lookback_days, "lim": limit}
        )
        return [(row[0], float(row[1])) for row in result.fetchall()]


async def store_post_embedding(
    *,
    post_id: int,
    text_for_embedding: str,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = EMBEDDING_MODEL,
) -> None:
    """Compute and store embedding for a channel post."""
    from app.infrastructure.db.models import ChannelPost

    try:
        embeddings = await get_embeddings([text_for_embedding], api_key=api_key, model=model)
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
        logger.warning("store_embedding_error", post_id=post_id, exc_info=True)
        # Non-fatal — post is already saved, embedding is optional
