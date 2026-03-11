"""Image discovery for channel posts — article parsing for high-quality images."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from app.agent.channel.http import SSRFError, get_http_client, is_safe_url
from app.core.logging import get_logger

logger = get_logger("channel.images")

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Maximum images to collect per post
MAX_IMAGES_PER_POST = 3


async def find_images_for_post(
    keywords: str,  # noqa: ARG001 — reserved for future image search API
    source_urls: list[str] | None = None,
    *,
    http_timeout: int = 10,
    max_images: int = MAX_IMAGES_PER_POST,
) -> list[str]:
    """Find high-quality images for a post from source article pages.

    Strategy per source URL:
    1. Extract OG/Twitter image (always full-size)
    2. Extract large images from article HTML body

    Returns a deduplicated list of image URLs (up to *max_images*).
    """
    if not source_urls:
        return []

    seen: set[str] = set()
    images: list[str] = []

    for url in source_urls[:3]:
        found = await _extract_article_images(url, http_timeout=http_timeout, max_images=max_images)
        for img in found:
            if img not in seen and len(images) < max_images:
                seen.add(img)
                images.append(img)

    if images:
        logger.info("images_found", count=len(images), first=images[0][:80])
    return images


async def find_image_for_post(
    keywords: str,
    source_urls: list[str] | None = None,
    *,
    http_timeout: int = 10,
) -> str | None:
    """Find the best single image for a post. Backward-compatible wrapper."""
    images = await find_images_for_post(keywords, source_urls, http_timeout=http_timeout, max_images=1)
    return images[0] if images else None


# ---------------------------------------------------------------------------
# OG / meta tag patterns
# ---------------------------------------------------------------------------

_OG_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', re.I),
    re.compile(r'<meta\s+name=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']og:image["\']', re.I),
    re.compile(r'<meta\s+(?:property|name)=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']twitter:image["\']', re.I),
]

# Image tags in HTML body
_IMG_SRC_RE = re.compile(r'<img\s[^>]*src=["\']([^"\']+)["\']', re.I)

# Skip tiny / irrelevant images
_SKIP_PATTERNS = re.compile(
    r"(favicon|icon|logo|avatar|pixel|track|badge|button|emoji|1x1|sprite|spacer|blank|ad[_-])",
    re.I,
)

# Prefer images with size hints — look for width/height attributes
_IMG_SIZE_RE = re.compile(r'<img\s[^>]*(?:width|data-width)=["\']?(\d+)[^>]*src=["\']([^"\']+)["\']', re.I)
_IMG_SIZE_RE_ALT = re.compile(r'<img\s[^>]*src=["\']([^"\']+)["\'][^>]*(?:width|data-width)=["\']?(\d+)', re.I)


async def _extract_article_images(
    url: str,
    *,
    http_timeout: int = 10,
    max_images: int = MAX_IMAGES_PER_POST,
) -> list[str]:
    """Extract high-quality images from a web page.

    Priority:
    1. OG/Twitter image meta tags (always full resolution)
    2. Large <img> tags from article body (width >= 400px or likely content images)
    """
    if not await is_safe_url(url):
        logger.warning("ssrf_blocked", url=url[:80])
        return []

    try:
        client = get_http_client(timeout=http_timeout)
        resp = await client.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=httpx.Timeout(http_timeout),
        )
        resp.raise_for_status()
    except SSRFError:
        logger.warning("ssrf_blocked", url=url[:80])
        return []
    except Exception:
        logger.debug("article_fetch_failed", url=url[:80])
        return []

    html = resp.text[:200_000]  # Read more HTML to find article images
    images: list[str] = []
    seen: set[str] = set()

    def _add(img_url: str) -> bool:
        """Add image if valid and not duplicate. Returns True if added."""
        normalized = _normalize_image_url(img_url, url)
        if not normalized or normalized in seen:
            return False
        # Also check base URL without query params to avoid same image at different sizes
        base_url = normalized.split("?")[0]
        if base_url in seen:
            return False
        if not _is_valid_image_url(normalized) or _SKIP_PATTERNS.search(normalized):
            return False
        seen.add(normalized)
        seen.add(base_url)
        images.append(normalized)
        return len(images) >= max_images

    # 1. OG / Twitter image (highest priority — always full resolution)
    for pattern in _OG_PATTERNS:
        match = pattern.search(html)
        if match and _add(match.group(1)):
            return images

    # 2. Large images from body (prefer those with width >= 400)
    for match in _IMG_SIZE_RE.finditer(html):
        width = int(match.group(1))
        if width >= 400 and _add(match.group(2)):
            return images

    for match in _IMG_SIZE_RE_ALT.finditer(html):
        width = int(match.group(2))
        if width >= 400 and _add(match.group(1)):
            return images

    # 3. Fallback: any plausible <img> that looks like content (skip small ones)
    for match in _IMG_SRC_RE.finditer(html):
        src = match.group(1)
        # Skip images with width hints in URL suggesting they're thumbnails
        if _has_small_width_hint(src):
            continue
        if _add(src):
            return images

    return images


def _normalize_image_url(raw_url: str, page_url: str) -> str | None:
    """Normalize image URL — handle relative paths and protocol-relative URLs."""
    raw_url = raw_url.strip()
    if not raw_url or raw_url.startswith("data:"):
        return None
    if raw_url.startswith("//"):
        return "https:" + raw_url
    if raw_url.startswith("/"):
        parsed = urlparse(page_url)
        return f"{parsed.scheme}://{parsed.netloc}{raw_url}"
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    return None


_SMALL_WIDTH_RE = re.compile(r"[?&]width=(\d+)|/width[=/](\d+)", re.I)


def _has_small_width_hint(url: str) -> bool:
    """Check if URL contains a width parameter suggesting a small/thumbnail image."""
    match = _SMALL_WIDTH_RE.search(url)
    if match:
        width = int(match.group(1) or match.group(2))
        return width < 400
    return False


def _is_valid_image_url(url: str) -> bool:
    """Check that URL likely points to a real image (not an icon/pixel)."""
    lower = url.lower().split("?")[0]
    has_ext = lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
    has_image_path = any(kw in lower for kw in ("image", "photo", "media", "upload", "img", "picture"))
    return has_ext or has_image_path


def extract_rss_media_url(entry: object) -> str | None:
    """Extract media URL from a feedparser entry.

    Checks (in priority order):
    1. media_content[0]['url']
    2. media_thumbnail[0]['url']
    3. enclosures[0]['href'] (if image type)
    4. links with type='image/*'
    """
    media_content = getattr(entry, "media_content", None)
    if media_content and isinstance(media_content, list) and media_content:
        url = media_content[0].get("url")
        if url:
            return url

    media_thumb = getattr(entry, "media_thumbnail", None)
    if media_thumb and isinstance(media_thumb, list) and media_thumb:
        url = media_thumb[0].get("url")
        if url:
            return url

    enclosures = getattr(entry, "enclosures", None)
    if enclosures and isinstance(enclosures, list):
        for enc in enclosures:
            enc_type = enc.get("type", "")
            if "image" in enc_type:
                url = enc.get("href") or enc.get("url")
                if url:
                    return url

    links = getattr(entry, "links", None)
    if links and isinstance(links, list):
        for link in links:
            if "image" in link.get("type", ""):
                url = link.get("href")
                if url:
                    return url

    return None


# _is_safe_url has been moved to app.agent.channel.http.is_safe_url (async).
# Re-export for backward compatibility with external callers / tests.
_is_safe_url = is_safe_url
