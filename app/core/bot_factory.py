"""Centralized bot factory for creating Bot instances."""

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings


class BotFactory:
    """Factory for creating Bot instances with consistent configuration."""

    _instance: Bot | None = None

    @classmethod
    def create_bot(cls) -> Bot:
        """
        Create a new Bot instance with standard configuration.

        Returns:
            Bot instance configured with HTML parse mode
        """
        return Bot(token=settings.telegram.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    @classmethod
    def get_singleton_bot(cls) -> Bot:
        """
        Get a singleton Bot instance.

        This should be used when you need a shared bot instance
        across the application (e.g., in API endpoints).

        Returns:
            Singleton Bot instance
        """
        if cls._instance is None:
            cls._instance = cls.create_bot()
        return cls._instance

    @classmethod
    def reset_singleton(cls) -> None:
        """
        Reset singleton instance.

        Useful for testing or when bot configuration changes.
        """
        cls._instance = None


# Convenience functions
def create_bot() -> Bot:
    """Create a new Bot instance."""
    return BotFactory.create_bot()


def get_bot() -> Bot:
    """Get singleton Bot instance."""
    return BotFactory.get_singleton_bot()
