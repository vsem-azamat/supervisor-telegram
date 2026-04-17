"""Semantic deduplication using pgvector embeddings.

Public helpers:
- build_embedding_text: canonical text representation for an item (shared by store/query)
- compute_embedding: pure function returning a single vector (no DB access)
- filter_semantic_duplicates: removes items similar to recent posts (cross-source dedup)
- find_nearest_posts: returns most similar recent posts for a text

Design notes:
- Embeddings are now MANDATORY for dedup. On API failure, callers must halt — not
  pass items through unfiltered. Historical "graceful degradation" here produced
  silent duplicate spam.
- `store_post_embedding` has been removed: callers must assign the vector to the
  ORM object within the same session that created the post, otherwise a READ
  COMMITTED new session cannot see the uncommitted row.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import text

from app.agent.channel.embeddings import EMBEDDING_MODEL, get_embeddings
from app.agent.channel.exceptions import EmbeddingError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.semantic_dedup")

# Defaults mirror ChannelAgentSettings so library-only callers (tests, scripts)
# get the same behavior as the running pipeline without depending on settings.
# Changing these affects vector comparability — keep in lockstep with config.
DEFAULT_EMBED_BODY_CHARS = 100
DEFAULT_QUERY_SNIPPET_CHARS = 200
DEFAULT_LOOKBACK_DAYS = 7
ERROR_RESPONSE_LOG_CHARS = 300


def build_embedding_text(title: str, body: str, *, body_chars: int = DEFAULT_EMBED_BODY_CHARS) -> str:
    """Canonical text used for embedding — must match for store and query sides."""
    return f"{title} {body[:body_chars]}"


def format_vector(embedding: list[float]) -> str:
    """Format embedding as pgvector-compatible string with explicit precision."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


def _describe_http_error(exc: BaseException) -> dict[str, object]:
    """Extract structured fields for logging from an httpx exception."""
    fields: dict[str, object] = {"error": str(exc), "error_type": type(exc).__name__}
    if isinstance(exc, httpx.HTTPStatusError):
        fields["http_status"] = exc.response.status_code
        with contextlib.suppress(Exception):
            fields["response_body"] = exc.response.text[:ERROR_RESPONSE_LOG_CHARS]
    return fields


async def compute_embedding(
    embed_text: str,
    *,
    api_key: str,
    model: str = EMBEDDING_MODEL,
) -> list[float]:
    """Compute a single embedding vector. Raises EmbeddingError on failure."""
    if not api_key:
        raise EmbeddingError("missing_api_key")
    try:
        vectors = await get_embeddings([embed_text], api_key=api_key, model=model)
    except Exception as exc:
        logger.warning("compute_embedding_failed", model=model, **_describe_http_error(exc))
        raise EmbeddingError(str(exc)) from exc
    if not vectors:
        raise EmbeddingError("empty_embedding_response")
    return vectors[0]


async def filter_semantic_duplicates(
    items: list[ContentItem],
    *,
    channel_id: int,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = EMBEDDING_MODEL,
    threshold: float = 0.85,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[ContentItem]:
    """Filter out items semantically similar to recent posts.

    Raises EmbeddingError if the embedding API is unavailable — callers MUST
    halt rather than publish unfiltered content.
    """
    if not items:
        return []

    texts = [build_embedding_text(item.title, item.body) for item in items]

    try:
        embeddings = await get_embeddings(texts, api_key=api_key, model=model)
    except Exception as exc:
        logger.warning(
            "filter_semantic_duplicates_api_error",
            channel_id=channel_id,
            model=model,
            items=len(items),
            **_describe_http_error(exc),
        )
        raise EmbeddingError(str(exc)) from exc

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
    logger.info(
        "semantic_dedup_done",
        channel_id=channel_id,
        total=len(items),
        filtered=filtered_count,
        remaining=len(unique_items),
        threshold=threshold,
        lookback_days=lookback_days,
    )

    return unique_items


async def _find_similar_indices(
    *,
    embeddings: list[list[float]],
    channel_id: int,
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
    channel_id: int,
    api_key: str,
    session_maker: async_sessionmaker[AsyncSession],
    model: str = EMBEDDING_MODEL,
    limit: int = 5,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    query_snippet_chars: int = DEFAULT_QUERY_SNIPPET_CHARS,
) -> list[tuple[str, float]]:
    """Find posts most similar to the given text.

    Returns list of (title, similarity_score) tuples, ordered by similarity desc.
    Raises EmbeddingError on embedding API failure.
    """
    try:
        embeddings = await get_embeddings([text_for_embedding[:query_snippet_chars]], api_key=api_key, model=model)
    except Exception as exc:
        logger.warning(
            "find_nearest_posts_api_error",
            channel_id=channel_id,
            model=model,
            **_describe_http_error(exc),
        )
        raise EmbeddingError(str(exc)) from exc

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
