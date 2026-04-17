"""Business logic for review-agent image tools.

Kept as free functions (``*_op`` suffix) so they can be tested without the
PydanticAI tool wrapper. The ``agent.py`` file imports these and exposes them
as ``@agent.tool``s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.channel.brave_search import brave_image_search
from app.channel.image_pipeline.filter import cheap_filter
from app.channel.image_pipeline.models import ImageCandidate
from app.channel.image_pipeline.score import vision_score
from app.core.enums import PostStatus
from app.core.logging import get_logger
from app.db.models import ChannelPost

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = get_logger("channel.review.image_tools")

MIN_POOL_QUALITY = 5
MIN_POOL_RELEVANCE = 4


@dataclass
class ImageToolsDeps:
    session_maker: async_sessionmaker
    post_id: int
    channel_id: int
    api_key: str
    vision_model: str
    brave_api_key: str


# ---------------------------------------------------------------------------
# list_images
# ---------------------------------------------------------------------------


async def list_images_op(deps: ImageToolsDeps) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."

    selected = post.image_urls or []
    pool = post.image_candidates or []

    if not selected and not pool:
        return "No images. Pool is empty. Use `find_and_add_image` or `add_image_url` to add some."

    lines = []
    if selected:
        lines.append(f"Selected ({len(selected)}):")
        for i, url in enumerate(selected):
            cand = _find_candidate(pool, url)
            desc = cand.description if cand else ""
            q = cand.quality_score if cand else None
            lines.append(f"  [{i}] {url}  q={q}  — {desc}")
    else:
        lines.append("Selected: (empty)")

    if pool:
        lines.append("")
        lines.append(f"Pool ({len(pool)} total):")
        for i, p in enumerate(pool):
            cand = ImageCandidate.model_validate(p)
            mark = "✓" if cand.selected else " "
            lines.append(
                f"  [{i}] {mark} q={cand.quality_score} r={cand.relevance_score} src={cand.source}"
                f"  — {cand.description}  ({cand.url})"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# use_candidate
# ---------------------------------------------------------------------------


async def use_candidate_op(deps: ImageToolsDeps, pool_index: int, position: int | None = None) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    pool = post.image_candidates or []
    if pool_index < 0 or pool_index >= len(pool):
        return f"Invalid pool_index {pool_index}: pool has {len(pool)} items."

    candidate = ImageCandidate.model_validate(pool[pool_index])
    urls = list(post.image_urls or [])
    if candidate.url in urls:
        return f"Image already selected at position {urls.index(candidate.url)}."

    if position is None or position >= len(urls):
        urls.append(candidate.url)
    else:
        urls.insert(max(position, 0), candidate.url)

    pool[pool_index]["selected"] = True
    await _save_and_refresh(deps, urls, pool)
    return f"Added candidate [{pool_index}] ({candidate.url}) to position {urls.index(candidate.url)}."


# ---------------------------------------------------------------------------
# add_image_url
# ---------------------------------------------------------------------------


async def add_image_url_op(deps: ImageToolsDeps, url: str, position: int | None = None) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    filtered = await cheap_filter([url])
    if not filtered:
        return f"Rejected: {url} did not pass quality heuristics (too small / wrong aspect / logo-like)."

    scored = await vision_score(
        filtered,
        title=post.title or "",
        api_key=deps.api_key,
        model=deps.vision_model,
    )
    if not scored:
        return f"Rejected: vision model flagged {url} as logo/text-slide/low-relevance."

    best = scored[0]
    new_cand = ImageCandidate(
        url=best.url,
        source="reviewer_added",
        width=best.width,
        height=best.height,
        quality_score=best.quality_score,
        relevance_score=best.relevance_score,
        is_logo=best.is_logo,
        is_text_slide=best.is_text_slide,
        description=best.description,
        selected=True,
    )
    pool = list(post.image_candidates or [])
    pool.append(new_cand.model_dump())

    urls = list(post.image_urls or [])
    if position is None or position >= len(urls):
        urls.append(new_cand.url)
    else:
        urls.insert(max(position, 0), new_cand.url)

    await _save_and_refresh(deps, urls, pool)
    return f"Added {new_cand.url} (q={new_cand.quality_score}, r={new_cand.relevance_score})."


# ---------------------------------------------------------------------------
# find_and_add_image
# ---------------------------------------------------------------------------


async def find_and_add_image_op(deps: ImageToolsDeps, query: str) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."
    results = await brave_image_search(deps.brave_api_key, query, count=6)
    if not results:
        return f"No image results for '{query}'."
    urls: list[str] = [u for r in results if (u := r.get("url", ""))]

    filtered = await cheap_filter(urls[:5])
    if not filtered:
        return f"No candidate from '{query}' passed quality heuristics."

    scored = await vision_score(
        filtered,
        title=post.title or "",
        api_key=deps.api_key,
        model=deps.vision_model,
    )
    if not scored:
        return f"All candidates from '{query}' were flagged by the vision model."

    best = scored[0]
    new_cand = ImageCandidate(
        url=best.url,
        source="brave_image",
        width=best.width,
        height=best.height,
        quality_score=best.quality_score,
        relevance_score=best.relevance_score,
        is_logo=best.is_logo,
        is_text_slide=best.is_text_slide,
        description=best.description,
        selected=False,  # not auto-selected
    )
    pool = list(post.image_candidates or [])
    pool.append(new_cand.model_dump())
    await _save_and_refresh(deps, post.image_urls or [], pool)
    return (
        f"Added to pool: {new_cand.url}  q={new_cand.quality_score}  r={new_cand.relevance_score}."
        f"  Call `use_candidate` to select it."
    )


# ---------------------------------------------------------------------------
# remove_image
# ---------------------------------------------------------------------------


async def remove_image_op(deps: ImageToolsDeps, position: int) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    urls = list(post.image_urls or [])
    if position < 0 or position >= len(urls):
        return f"Invalid position {position}: post has {len(urls)} images."

    removed_url = urls.pop(position)
    pool = list(post.image_candidates or [])
    for entry in pool:
        if entry.get("url") == removed_url:
            entry["selected"] = False
    await _save_and_refresh(deps, urls, pool)
    return f"Removed position {position} ({removed_url})."


# ---------------------------------------------------------------------------
# reorder_images
# ---------------------------------------------------------------------------


async def reorder_images_op(deps: ImageToolsDeps, order: list[int]) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    urls = list(post.image_urls or [])
    if len(order) != len(urls) or sorted(order) != list(range(len(urls))):
        return f"Invalid order length/values: got {order}, expected a permutation of 0..{len(urls) - 1}."

    new_urls = [urls[i] for i in order]
    await _save_and_refresh(deps, new_urls, post.image_candidates or [])
    return f"Reordered images: {new_urls}"


# ---------------------------------------------------------------------------
# clear_images
# ---------------------------------------------------------------------------


async def clear_images_op(deps: ImageToolsDeps) -> str:
    post = await _load_post(deps)
    if post is None:
        return "Post not found."
    if post.status != PostStatus.DRAFT:
        return f"Cannot edit: post is {post.status}."

    pool = list(post.image_candidates or [])
    for entry in pool:
        entry["selected"] = False
    await _save_and_refresh(deps, [], pool)
    return "All images removed from post (pool kept for re-use)."


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _load_post(deps: ImageToolsDeps) -> ChannelPost | None:
    async with deps.session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == deps.post_id))
        return r.scalar_one_or_none()


async def _save_and_refresh(
    deps: ImageToolsDeps,
    new_urls: list[str],
    new_pool: list[dict],
) -> None:
    """Update DB with new image_urls + image_candidates + image_phashes in one transaction.

    Always writes ``new_urls`` as-is (even if empty list) so callers that
    explicitly clear images get ``[]`` back rather than ``None``.

    Also recomputes ``image_phashes`` from the pool's stored phash values for
    the selected URLs — so future posts' dedup query sees what was actually
    published, not the original pipeline's selection.
    """
    # Build the selected-phashes list from the pool (not from recomputing hashes —
    # the pool already carries phashes from cheap_filter + phash_dedup).
    url_to_phash: dict[str, str] = {}
    for entry in new_pool:
        url = entry.get("url")
        phash = entry.get("phash")
        if url and phash:
            url_to_phash[url] = phash
    new_phashes = [url_to_phash[u] for u in new_urls if u in url_to_phash]

    async with deps.session_maker() as session:
        r = await session.execute(select(ChannelPost).where(ChannelPost.id == deps.post_id))
        fresh = r.scalar_one_or_none()
        if fresh is None:
            return
        # Store the list directly — preserve empty list semantics for callers
        # that explicitly clear (so tests can assert == []).
        fresh.image_urls = new_urls
        fresh.image_url = new_urls[0] if new_urls else None
        fresh.image_candidates = new_pool if new_pool else None
        fresh.image_phashes = new_phashes if new_phashes else None
        await session.commit()


def _find_candidate(pool: list[dict], url: str) -> ImageCandidate | None:
    for entry in pool:
        if entry.get("url") == url:
            try:
                return ImageCandidate.model_validate(entry)
            except Exception:
                return None
    return None
