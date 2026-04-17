"""Stage 1 of the image pipeline: cheap heuristic filters.

Downloads each candidate URL (SSRF-safe), opens with Pillow, drops anything
that's obviously unusable (too small, weird aspect, low entropy, oversize
file-vs-area ratio). No paid APIs are called.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.channel.http import SSRFError, safe_fetch
from app.core.logging import get_logger

logger = get_logger("channel.image_pipeline.filter")

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
MIN_WIDTH = 600
MIN_HEIGHT = 400
MAX_ASPECT_RATIO = 3.0
MIN_UNIQUE_COLORS = 30
MIN_FILE_SIZE_FOR_LARGE_IMAGES = 20_000
LARGE_IMAGE_AREA = 500_000
DOWNLOAD_TIMEOUT_SECONDS = 10

# Support both Pillow 12+ (Image.Palette.ADAPTIVE) and older (Image.ADAPTIVE)
try:
    _ADAPTIVE = Image.Palette.ADAPTIVE
except AttributeError:
    _ADAPTIVE = Image.ADAPTIVE  # type: ignore[attr-defined]


@dataclass(slots=True)
class FilteredImage:
    """An image that passed ``cheap_filter``. Carries bytes so downstream
    stages (vision_score, phash_dedup) don't re-download. ``phash`` and
    ``is_duplicate`` are populated by ``phash_dedup_against``."""

    url: str
    width: int
    height: int
    bytes_: bytes
    phash: str | None = None
    is_duplicate: bool = False


async def cheap_filter(urls: list[str]) -> list[FilteredImage]:
    """Download candidates in parallel and keep only those that pass the checks.

    Failures (network, SSRF, decode, threshold) silently drop that URL; other
    URLs are unaffected. Returns results in the same order as input, minus
    dropped items.
    """
    if not urls:
        return []

    tasks = [asyncio.create_task(_check_one(u)) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    kept: list[FilteredImage] = []
    for url, r in zip(urls, results, strict=True):
        if isinstance(r, FilteredImage):
            kept.append(r)
        elif isinstance(r, Exception):
            logger.debug("image_filter_failed", url=url[:120], error=type(r).__name__)
    return kept


async def _check_one(url: str) -> FilteredImage | None:
    try:
        resp = await safe_fetch(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    except SSRFError:
        logger.debug("image_filter_ssrf_blocked", url=url[:120])
        return None
    except Exception as exc:
        logger.debug("image_filter_download_failed", url=url[:120], error=type(exc).__name__)
        return None

    data = resp.content
    if len(data) > MAX_BYTES:
        logger.debug("image_filter_oversize", url=url[:120], bytes=len(data))
        return None

    try:
        img = Image.open(BytesIO(data))
        img.verify()  # structural check
        img = Image.open(BytesIO(data))  # reopen after verify() consumes it
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        logger.debug("image_filter_decode_failed", url=url[:120])
        return None

    w, h = img.size
    if w < MIN_WIDTH or h < MIN_HEIGHT:
        logger.debug("image_filter_too_small", url=url[:120], w=w, h=h)
        return None

    if max(w, h) / min(w, h) > MAX_ASPECT_RATIO:
        logger.debug("image_filter_aspect", url=url[:120], w=w, h=h)
        return None

    # Palette mode supports max 256 colors; quantize to that and count unique entries
    palette = img.convert("P", palette=_ADAPTIVE, colors=256)
    uniques = palette.getcolors(maxcolors=256)
    if uniques is None or len(uniques) < MIN_UNIQUE_COLORS:
        logger.debug("image_filter_low_entropy", url=url[:120], uniques=len(uniques or []))
        return None

    if w * h > LARGE_IMAGE_AREA and len(data) < MIN_FILE_SIZE_FOR_LARGE_IMAGES:
        logger.debug("image_filter_suspicious_size_ratio", url=url[:120], bytes=len(data), area=w * h)
        return None

    return FilteredImage(url=url, width=w, height=h, bytes_=data)
