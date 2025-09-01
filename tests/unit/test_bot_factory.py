"""Tests for bot factory."""

from unittest.mock import patch

from aiogram import Bot
from app.core.bot_factory import BotFactory, create_bot, get_bot


class TestBotFactory:
    """Test bot factory."""

    def test_create_bot_returns_bot_instance(self):
        """Test that create_bot returns a Bot instance."""
        with patch("app.core.bot_factory.settings.telegram.token", "123456:ABC-DEF1234567890"):
            bot = BotFactory.create_bot()
            assert isinstance(bot, Bot)

    def test_get_singleton_bot_returns_same_instance(self):
        """Test that singleton bot returns same instance."""
        with patch("app.core.bot_factory.settings.telegram.token", "123456:ABC-DEF1234567890"):
            # Reset singleton first
            BotFactory.reset_singleton()

            bot1 = BotFactory.get_singleton_bot()
            bot2 = BotFactory.get_singleton_bot()

            assert bot1 is bot2
            assert isinstance(bot1, Bot)

    def test_reset_singleton(self):
        """Test resetting singleton instance."""
        with patch("app.core.bot_factory.settings.telegram.token", "123456:ABC-DEF1234567890"):
            # Get initial instance
            bot1 = BotFactory.get_singleton_bot()

            # Reset and get new instance
            BotFactory.reset_singleton()
            bot2 = BotFactory.get_singleton_bot()

            # Should be different instances
            assert bot1 is not bot2

    def test_create_bot_convenience_function(self):
        """Test create_bot convenience function."""
        with patch("app.core.bot_factory.settings.telegram.token", "123456:ABC-DEF1234567890"):
            bot = create_bot()
            assert isinstance(bot, Bot)

    def test_get_bot_convenience_function(self):
        """Test get_bot convenience function."""
        with patch("app.core.bot_factory.settings.telegram.token", "123456:ABC-DEF1234567890"):
            BotFactory.reset_singleton()  # Reset first
            bot = get_bot()
            assert isinstance(bot, Bot)
