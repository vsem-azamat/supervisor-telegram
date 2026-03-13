"""Tests for report service."""

from unittest.mock import AsyncMock, patch

import pytest
from app.moderation import report


@pytest.mark.unit
class TestReportService:
    """Test report service."""

    @pytest.fixture
    def mock_bot(self):
        return AsyncMock()

    @pytest.fixture
    def mock_reporter(self):
        user = AsyncMock()
        user.id = 123456789
        user.username = "reporter"
        user.first_name = "John"
        return user

    @pytest.fixture
    def mock_reported(self):
        user = AsyncMock()
        user.id = 987654321
        user.username = "reported"
        user.first_name = "Jane"
        return user

    @pytest.fixture
    def mock_message(self):
        message = AsyncMock()
        message.text = "This is a reported message"
        message.message_id = 456
        return message

    async def test_report_to_moderators(self, mock_bot, mock_reporter, mock_reported, mock_message):
        """Test reporting to moderators uses markdown+entities (no HTML)."""
        mock_message.chat.title = "Test Chat"
        mock_message.chat.username = "testchat"
        mock_message.chat.id = -1001234567890

        mock_reporter.full_name = "John Reporter"
        mock_reported.full_name = "Jane Reported"

        with patch("app.moderation.report.settings") as mock_settings:
            mock_settings.admin.default_report_chat_id = -1001234567890

            await report.report_to_moderators(mock_bot, mock_reporter, mock_reported, mock_message)

            mock_bot.send_message.assert_called_once()
            call_args = mock_bot.send_message.call_args

            assert call_args[1]["chat_id"] == -1001234567890
            assert call_args[1]["parse_mode"] is None
            assert call_args[1].get("entities") is not None

            message_text = call_args[1]["text"]
            assert "This is a reported message" in message_text
