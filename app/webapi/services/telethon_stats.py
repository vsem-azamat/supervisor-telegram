"""Cached wrapper around TelethonClient for webapi endpoints.

Spec: docs/superpowers/specs/2026-04-21-web-ui-scope-design.md — Tech layer.

Degrades gracefully when telethon is None or not connected: member count
becomes None, post-views becomes an empty dict. Callers treat missing data
as "zero", so the UI still renders without errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cachetools import TTLCache

if TYPE_CHECKING:
    from app.telethon.telethon_client import TelethonClient

_MEMBER_COUNT_TTL_SECONDS = 300
_POST_VIEWS_TTL_SECONDS = 600
_CACHE_MAXSIZE = 1024


class TelethonStatsService:
    """Per-request-or-longer-lived cache over a few Telethon reads.

    Lifetime: attached to the FastAPI app (one instance per process), so
    caches persist across requests. That's the whole point — it protects
    the Telethon account from flood-wait when multiple tabs refresh.
    """

    def __init__(self, telethon: TelethonClient | None) -> None:
        self._telethon = telethon
        self._member_cache: TTLCache[int, int | None] = TTLCache(maxsize=_CACHE_MAXSIZE, ttl=_MEMBER_COUNT_TTL_SECONDS)
        self._views_cache: TTLCache[tuple[int, tuple[int, ...]], dict[int, int]] = TTLCache(
            maxsize=_CACHE_MAXSIZE, ttl=_POST_VIEWS_TTL_SECONDS
        )

    async def get_member_count(self, chat_id: int) -> int | None:
        if self._telethon is None or not self._telethon.is_available:
            return None
        if chat_id in self._member_cache:
            return self._member_cache[chat_id]
        info = await self._telethon.get_chat_info(chat_id)
        count = info.member_count if info is not None else None
        self._member_cache[chat_id] = count
        return count

    async def get_post_views_batch(self, chat_id: int, message_ids: list[int]) -> dict[int, int]:
        if self._telethon is None or not self._telethon.is_available or not message_ids:
            return {}
        key = (chat_id, tuple(sorted(message_ids)))
        if key in self._views_cache:
            return self._views_cache[key]
        views = await self._telethon.get_post_views(chat_id, list(message_ids))
        self._views_cache[key] = views
        return views
