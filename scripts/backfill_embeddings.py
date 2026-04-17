"""Backfill embeddings for ChannelPost rows whose embedding column is NULL.

Usage:
    uv run python scripts/backfill_embeddings.py [--batch 32] [--days 30]

Safe to re-run: only rows with ``embedding IS NULL`` are touched. The text used
is the same ``build_embedding_text`` the live pipeline uses, so back-filled
vectors are directly comparable to newly stored ones.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.channel.embeddings import EMBEDDING_MODEL, get_embeddings
from app.channel.semantic_dedup import build_embedding_text
from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.db.models import ChannelPost
from app.infrastructure.db.session import close_db, create_session_maker
from dotenv import load_dotenv
from sqlalchemy import select, update

logger = get_logger("backfill_embeddings")


def _extract_source_text(post: ChannelPost) -> str:
    """Replay the same text that ``create_review_post`` embeds."""
    if post.source_items:
        first = post.source_items[0]
        title = str(first.get("title") or post.title or "")
        body = str(first.get("summary") or first.get("body") or "")
        if title or body:
            return build_embedding_text(title, body)
    return build_embedding_text(post.title or "", post.post_text or "")


async def _backfill(batch_size: int, lookback_days: int | None, dry_run: bool) -> int:
    session_maker = create_session_maker()
    api_key = settings.openrouter.api_key
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not configured")

    model = settings.channel.embedding_model or EMBEDDING_MODEL

    async with session_maker() as session:
        stmt = select(ChannelPost).where(ChannelPost.embedding.is_(None))
        if lookback_days is not None:
            from sqlalchemy import text as sa_text

            stmt = stmt.where(
                ChannelPost.created_at > sa_text("NOW() - make_interval(days => :d)").bindparams(d=lookback_days)
            )
        stmt = stmt.order_by(ChannelPost.id)
        result = await session.execute(stmt)
        posts = list(result.scalars().all())

    logger.info("backfill_planning", candidates=len(posts), batch_size=batch_size, dry_run=dry_run)
    if dry_run or not posts:
        return len(posts)

    processed = 0
    for start in range(0, len(posts), batch_size):
        batch = posts[start : start + batch_size]
        texts = [_extract_source_text(p) for p in batch]
        try:
            vectors = await get_embeddings(texts, api_key=api_key, model=model)
        except Exception as exc:
            logger.warning(
                "backfill_batch_failed",
                batch_start=start,
                batch_size=len(batch),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue

        async with session_maker() as session:
            for post, vec in zip(batch, vectors, strict=True):
                await session.execute(
                    update(ChannelPost).where(ChannelPost.id == post.id).values(embedding=vec, embedding_model=model)
                )
            await session.commit()

        processed += len(batch)
        logger.info("backfill_progress", processed=processed, total=len(posts))

    logger.info("backfill_complete", processed=processed, total=len(posts), model=model)
    return processed


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--batch",
        type=int,
        default=settings.channel.backfill_batch_size,
        help="Embeddings API batch size (default from CHANNEL_BACKFILL_BATCH_SIZE)",
    )
    p.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only backfill posts from the last N days (default: all missing)",
    )
    p.add_argument("--dry-run", action="store_true", help="Count candidates without calling the API")
    return p.parse_args()


async def _main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    args = _parse_args()
    try:
        count = await _backfill(batch_size=args.batch, lookback_days=args.days, dry_run=args.dry_run)
        print(f"{'DRY RUN — ' if args.dry_run else ''}processed {count} posts")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(_main())
