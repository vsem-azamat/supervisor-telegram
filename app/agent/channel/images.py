"""Image discovery for channel posts — RSS media extraction + OG image parsing."""

from __future__ import annotations

import re

import httpx

from app.core.logging import get_logger

logger = get_logger("channel.images")

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def find_image_for_post(
    keywords: str,  # noqa: ARG001
    source_urls: list[str] | None = None,
    *,
    http_timeout: int = 10,
) -> str | None:
    """Find the best image for a post.

    Strategy:
    1. Try extracting OG image from source article URLs
    2. Try extracting any large image from article HTML

    ``keywords`` is reserved for future image search API integration.

    Returns an image URL or None.
    """
    if not source_urls:
        return None

    for url in source_urls[:3]:
        image = await _extract_article_image(url, http_timeout=http_timeout)
        if image:
            logger.info("article_image_found", url=url[:60], image=image[:80])
            return image

    return None


# Multiple regex patterns for OG image (sites vary in attribute order)
_OG_PATTERNS = [
    re.compile(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', re.I),
    re.compile(r'<meta\s+name=["\']og:image["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']og:image["\']', re.I),
    # twitter:image as fallback
    re.compile(r'<meta\s+(?:property|name)=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\']twitter:image["\']', re.I),
]

# Extract first large image from HTML (as last resort)
_IMG_SRC_RE = re.compile(r'<img\s[^>]*src=["\']([^"\']+)["\']', re.I)

# Skip tiny images (icons, tracking pixels, avatars)
_SKIP_PATTERNS = re.compile(r"(favicon|icon|logo|avatar|pixel|track|badge|button|emoji|1x1)", re.I)


async def _extract_article_image(url: str, *, http_timeout: int = 10) -> str | None:
    """Extract the best image from a web page — OG image first, then first large img tag."""
    try:
        async with httpx.AsyncClient(
            timeout=http_timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception:
        logger.debug("article_fetch_failed", url=url[:80])
        return None

    html = resp.text[:100_000]

    # 1. Try OG / Twitter image meta tags
    for pattern in _OG_PATTERNS:
        match = pattern.search(html)
        if match:
            image_url = _normalize_image_url(match.group(1), url)
            if image_url and _is_valid_image_url(image_url):
                return image_url

    # 2. Fallback: find first plausible <img> in article body
    for match in _IMG_SRC_RE.finditer(html):
        img_url = _normalize_image_url(match.group(1), url)
        if img_url and _is_valid_image_url(img_url) and not _SKIP_PATTERNS.search(img_url):
            return img_url

    return None


def _normalize_image_url(raw_url: str, page_url: str) -> str | None:
    """Normalize image URL — handle relative paths and protocol-relative URLs."""
    raw_url = raw_url.strip()
    if raw_url.startswith("//"):
        return "https:" + raw_url
    if raw_url.startswith("/"):
        # Relative URL — resolve against page domain
        from urllib.parse import urlparse

        parsed = urlparse(page_url)
        return f"{parsed.scheme}://{parsed.netloc}{raw_url}"
    if raw_url.startswith(("http://", "https://")):
        return raw_url
    return None


def _is_valid_image_url(url: str) -> bool:
    """Check that URL likely points to a real image (not an icon/pixel)."""
    lower = url.lower().split("?")[0]
    has_ext = lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
    has_image_path = "image" in lower or "photo" in lower or "media" in lower or "upload" in lower
    return has_ext or has_image_path


def extract_rss_media_url(entry: object) -> str | None:
    """Extract media URL from a feedparser entry.

    Checks (in priority order):
    1. media_content[0]['url']
    2. media_thumbnail[0]['url']
    3. enclosures[0]['href'] (if image type)
    4. links with type='image/*'
    """
    # media:content
    media_content = getattr(entry, "media_content", None)
    if media_content and isinstance(media_content, list) and media_content:
        url = media_content[0].get("url")
        if url:
            return url

    # media:thumbnail
    media_thumb = getattr(entry, "media_thumbnail", None)
    if media_thumb and isinstance(media_thumb, list) and media_thumb:
        url = media_thumb[0].get("url")
        if url:
            return url

    # enclosures
    enclosures = getattr(entry, "enclosures", None)
    if enclosures and isinstance(enclosures, list):
        for enc in enclosures:
            enc_type = enc.get("type", "")
            if "image" in enc_type:
                url = enc.get("href") or enc.get("url")
                if url:
                    return url

    # links with image type
    links = getattr(entry, "links", None)
    if links and isinstance(links, list):
        for link in links:
            if "image" in link.get("type", ""):
                url = link.get("href")
                if url:
                    return url

    return None
