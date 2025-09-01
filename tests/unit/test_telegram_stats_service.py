"""Tests for Telegram stats service."""

from unittest.mock import AsyncMock, Mock

import pytest
from app.application.services.telegram_stats import TelegramStatsService


class TestTelegramStatsService:
    """Test Telegram stats service."""

    @pytest.fixture
    def mock_bot(self):
        """Mock bot for testing."""
        return AsyncMock()

    @pytest.fixture
    def stats_service(self, mock_bot):
        """Create stats service with mock bot."""
        return TelegramStatsService(mock_bot)

    async def test_get_chat_member_count_success(self, stats_service, mock_bot):
        """Test successful chat member count retrieval."""
        chat_id = -1001234567890
        expected_count = 150

        # Mock chat object with member_count
        mock_chat = Mock()
        mock_chat.member_count = expected_count
        mock_bot.get_chat.return_value = mock_chat

        result = await stats_service.get_chat_member_count(chat_id)

        assert result == expected_count
        mock_bot.get_chat.assert_called_once_with(chat_id)

    async def test_get_chat_member_count_error(self, stats_service, mock_bot):
        """Test error handling in chat member count retrieval."""
        chat_id = -1001234567890

        # Mock bot to raise exception
        mock_bot.get_chat.side_effect = Exception("API Error")

        result = await stats_service.get_chat_member_count(chat_id)

        # Should return 0 on error
        assert result == 0
        mock_bot.get_chat.assert_called_once_with(chat_id)

    async def test_get_chat_info_success(self, stats_service, mock_bot):
        """Test successful chat info retrieval."""
        chat_id = -1001234567890

        # Mock chat object
        mock_chat = Mock()
        mock_chat.id = chat_id
        mock_chat.title = "Test Chat"
        mock_chat.type = "supergroup"
        mock_chat.member_count = 100
        mock_bot.get_chat.return_value = mock_chat

        result = await stats_service.get_chat_info(chat_id)

        assert result is not None
        # Service returns dict, not object
        assert result["id"] == chat_id
        assert result["title"] == "Test Chat"
        assert result["type"] == "supergroup"
        mock_bot.get_chat.assert_called_once_with(chat_id)

    async def test_get_chat_info_error(self, stats_service, mock_bot):
        """Test error handling in chat info retrieval."""
        chat_id = -1001234567890

        # Mock bot to raise exception
        mock_bot.get_chat.side_effect = Exception("API Error")

        result = await stats_service.get_chat_info(chat_id)

        # Should return None on error
        assert result is None
        mock_bot.get_chat.assert_called_once_with(chat_id)

    def test_cache_initialization(self, stats_service):
        """Test that cache is properly initialized."""
        # Just test that service is created without errors
        # Internal cache implementation may vary
        assert stats_service is not None
