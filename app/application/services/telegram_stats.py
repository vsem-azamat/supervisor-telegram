"""Service for collecting Telegram chat statistics with caching."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from app.core.logging import get_logger

logger = get_logger("telegram_stats")


class TelegramStatsCache:
    """Simple in-memory cache for Telegram API data."""

    def __init__(self, ttl_seconds: int = 300):  # 5 minutes default
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if datetime.now() > entry["expires_at"]:
            del self._cache[key]
            return None

        return entry["data"]

    def set(self, key: str, data: Any) -> None:
        """Set cached value with expiration."""
        self._cache[key] = {"data": data, "expires_at": datetime.now() + timedelta(seconds=self.ttl_seconds)}

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()


class TelegramStatsService:
    """Service for collecting Telegram statistics with caching."""

    def __init__(self, bot: Bot, cache_ttl: int = 300):
        self.bot = bot
        self.cache = TelegramStatsCache(cache_ttl)
        # Short-lived cache for detailed chat info
        self._detail_cache = TelegramStatsCache(ttl_seconds=60)

    async def get_chat_member_count(self, chat_id: int) -> int:
        """Get number of members in chat with caching."""
        cache_key = f"member_count_{chat_id}"

        # Try cache first
        cached_count = self.cache.get(cache_key)
        if cached_count is not None:
            logger.debug("Retrieved member count from cache", chat_id=chat_id, count=cached_count)
            return int(cached_count)

        try:
            # Get from Telegram API
            chat = await self.bot.get_chat(chat_id)
            member_count = getattr(chat, "member_count", 0) or 0

            # Cache the result
            self.cache.set(cache_key, member_count)

            logger.info("Retrieved member count from Telegram API", chat_id=chat_id, count=member_count)
            return member_count

        except TelegramBadRequest as e:
            logger.warning("Failed to get chat member count", chat_id=chat_id, error=str(e))
            # Return 0 if can't access chat
            return 0
        except Exception as e:
            logger.error("Unexpected error getting member count", chat_id=chat_id, error=str(e))
            return 0

    async def get_multiple_chat_member_counts(self, chat_ids: list[int]) -> dict[int, int]:
        """Get member counts for multiple chats efficiently."""
        results = {}

        # Check cache first for all chats
        uncached_chat_ids = []
        for chat_id in chat_ids:
            cached_count = self.cache.get(f"member_count_{chat_id}")
            if cached_count is not None:
                results[chat_id] = cached_count
            else:
                uncached_chat_ids.append(chat_id)

        if not uncached_chat_ids:
            logger.debug("All member counts retrieved from cache", total_chats=len(chat_ids))
            return results

        # Fetch uncached data concurrently with rate limiting
        logger.info("Fetching member counts from Telegram API", uncached_count=len(uncached_chat_ids))

        # Process in batches to avoid rate limits
        batch_size = 5  # Conservative rate limiting
        for i in range(0, len(uncached_chat_ids), batch_size):
            batch = uncached_chat_ids[i : i + batch_size]

            # Process batch concurrently
            tasks = [self.get_chat_member_count(chat_id) for chat_id in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Store results
            for chat_id, result in zip(batch, batch_results, strict=False):
                if isinstance(result, Exception):
                    logger.warning("Failed to get member count for chat", chat_id=chat_id, error=str(result))
                    results[chat_id] = 0
                else:
                    results[chat_id] = result

            # Small delay between batches
            if i + batch_size < len(uncached_chat_ids):
                await asyncio.sleep(0.5)

        return results

    async def get_chat_info(self, chat_id: int) -> dict[str, Any] | None:
        """Get comprehensive chat information with caching."""
        cache_key = f"chat_info_{chat_id}"

        # Try cache first
        cached_info = self._detail_cache.get(cache_key)
        if cached_info is not None:
            return dict(cached_info) if isinstance(cached_info, dict) else None

        try:
            chat = await self.bot.get_chat(chat_id)

            info = {
                "id": chat.id,
                "title": chat.title,
                "type": chat.type,
                "member_count": getattr(chat, "member_count", 0) or 0,
                "description": chat.description,
                "invite_link": chat.invite_link,
                "is_forum": getattr(chat, "is_forum", False),
            }

            # Cache with shorter TTL for detailed info
            self._detail_cache.set(cache_key, info)

            logger.info("Retrieved chat info from Telegram API", chat_id=chat_id)
            return info

        except TelegramBadRequest as e:
            logger.warning("Failed to get chat info", chat_id=chat_id, error=str(e))
            return None
        except Exception as e:
            logger.error("Unexpected error getting chat info", chat_id=chat_id, error=str(e))
            return None

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()
        logger.info("Telegram stats cache cleared")
