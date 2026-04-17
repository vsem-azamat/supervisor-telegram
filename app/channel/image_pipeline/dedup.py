"""Stage 3 of the image pipeline: pHash-based deduplication.

For each filtered candidate we compute a 64-bit perceptual hash, look up the
last N approved posts' stored hashes in the same channel, and drop candidates
whose Hamming distance to any recent hash is below the configured threshold.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import imagehash
from PIL import Image
from sqlalchemy import select

from app.core.enums import PostStatus
from app.core.logging import get_logger
from app.db.models import ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.channel.image_pipeline.filter import FilteredImage

logger = get_logger("channel.image_pipeline.dedup")

PHASH_HEX_LEN = 16  # 64-bit pHash = 16 hex chars


def compute_phash(image_bytes: bytes) -> str:
    """Return a 64-bit perceptual hash as a 16-char hex string.

    Raises whatever PIL / imagehash raise on bad input — callers handle it.
    """
    img = Image.open(BytesIO(image_bytes))
    h = imagehash.phash(img)  # 8×8 DCT = 64 bits by default
    return str(h)


def hamming_distance(a: str, b: str) -> int:
    """Hamming distance between two equal-length hex strings.

    Converts both to ints and xors, then popcount.
    """
    if len(a) != len(b):
        raise ValueError(f"hash length mismatch: {len(a)} vs {len(b)}")
    return (int(a, 16) ^ int(b, 16)).bit_count()


def phash_dedup_against(
    images: list[FilteredImage],
    recent_hashes: list[str],
    *,
    threshold: int,
) -> list[FilteredImage]:
    """Pure-function dedup: keep images whose pHash is > threshold from every
    recent hash. Mutates ``phash`` and ``is_duplicate`` on every input image
    (callers may want the annotation even on dropped items).
    """
    kept: list[FilteredImage] = []
    for img in images:
        try:
            img_hash = compute_phash(img.bytes_)
        except Exception:
            logger.warning("phash_compute_failed", url=img.url[:120], exc_info=True)
            # Cannot hash → cannot dedup. Best-effort: keep but mark no-hash.
            img.phash = None
            kept.append(img)
            continue

        img.phash = img_hash
        img.is_duplicate = any(hamming_distance(img_hash, h) <= threshold for h in recent_hashes)
        if img.is_duplicate:
            logger.info("phash_duplicate_dropped", url=img.url[:120], hash=img_hash)
            continue
        kept.append(img)
    return kept


async def recent_phashes_for_channel(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: int,
    *,
    lookback: int,
) -> list[str]:
    """Flatten ``image_phashes`` across the last ``lookback`` approved posts in
    this channel. Oldest posts first in the list does not matter — callers
    treat this as a set."""
    if lookback <= 0:
        return []
    async with session_maker() as session:
        stmt = (
            select(ChannelPost.image_phashes)
            .where(ChannelPost.channel_id == channel_id)
            .where(ChannelPost.status == PostStatus.APPROVED)
            .where(ChannelPost.image_phashes.isnot(None))
            .order_by(ChannelPost.created_at.desc())
            .limit(lookback)
        )
        rows = (await session.execute(stmt)).scalars().all()
    flat: list[str] = []
    for row in rows:
        if row:
            flat.extend(row)
    return flat


async def phash_dedup(
    session_maker: async_sessionmaker[AsyncSession],
    channel_id: int,
    images: list[FilteredImage],
    *,
    threshold: int,
    lookback: int,
) -> list[FilteredImage]:
    """End-to-end: fetch recent hashes from DB, then filter images against them."""
    if not images:
        return []
    try:
        recent = await recent_phashes_for_channel(session_maker, channel_id, lookback=lookback)
    except Exception:
        logger.warning("phash_lookup_failed_skipping_dedup", channel_id=channel_id, exc_info=True)
        # DB unavailable → best-effort: keep everything. compute_phash still runs
        # so downstream stores phash for future dedup.
        return phash_dedup_against(images, recent_hashes=[], threshold=threshold)

    return phash_dedup_against(images, recent_hashes=recent, threshold=threshold)
