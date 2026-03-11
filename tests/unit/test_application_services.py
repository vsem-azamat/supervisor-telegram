"""Tests for application services."""

from unittest.mock import AsyncMock, patch

import pytest
from app.application.services import buttons, report


@pytest.mark.unit
class TestButtonsService:
    """Test buttons service."""

    async def test_get_contacts_buttons(self):
        """Test getting contacts buttons."""
        # Act
        builder = await buttons.get_contacts_buttons()

        # Assert
        keyboard = builder.as_markup()
        assert len(keyboard.inline_keyboard) == 2  # Two rows (2 buttons, adjust(1))

        # Check first button (Dev)
        dev_button = keyboard.inline_keyboard[0][0]
        assert dev_button.text == "Dev"
        assert dev_button.url == "https://t.me/vsem_azamat"

        # Check second button (GitHub)
        github_button = keyboard.inline_keyboard[1][0]
        assert github_button.text == "GitHub"
        assert github_button.url == "https://github.com/vsem-azamat/moderator-bot"

    async def test_get_chat_buttons_empty(self):
        """Test getting chat buttons when no chats exist."""
        # Arrange
        mock_db = AsyncMock()

        with patch("app.application.services.buttons.ChatLinkRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_chat_links.return_value = []
            mock_repo_class.return_value = mock_repo

            # Act
            builder = await buttons.get_chat_buttons(mock_db)

            # Assert
            keyboard = builder.as_markup()
            assert len(keyboard.inline_keyboard) == 0

    async def test_get_chat_buttons_with_chats(self):
        """Test getting chat buttons with existing chats."""
        # Arrange
        mock_db = AsyncMock()
        mock_chat1 = AsyncMock()
        mock_chat1.text = "Chat 1"
        mock_chat1.link = "https://t.me/chat1"

        mock_chat2 = AsyncMock()
        mock_chat2.text = "Chat 2"
        mock_chat2.link = "https://t.me/chat2"

        with patch("app.application.services.buttons.ChatLinkRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_chat_links.return_value = [mock_chat1, mock_chat2]
            mock_repo_class.return_value = mock_repo

            # Act
            builder = await buttons.get_chat_buttons(mock_db)

            # Assert
            keyboard = builder.as_markup()
            assert len(keyboard.inline_keyboard) == 1  # One row with 2 buttons (adjust(2))
            assert len(keyboard.inline_keyboard[0]) == 2  # Two buttons in the row

            # Check buttons
            button1 = keyboard.inline_keyboard[0][0]
            assert button1.text == "Chat 1"
            assert button1.url == "https://t.me/chat1"

            button2 = keyboard.inline_keyboard[0][1]
            assert button2.text == "Chat 2"
            assert button2.url == "https://t.me/chat2"


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
        # Setup chat attributes needed by the new implementation
        mock_message.chat.title = "Test Chat"
        mock_message.chat.username = "testchat"
        mock_message.chat.id = -1001234567890

        mock_reporter.full_name = "John Reporter"
        mock_reported.full_name = "Jane Reported"

        with patch("app.application.services.report.settings") as mock_settings:
            mock_settings.admin.default_report_chat_id = -1001234567890

            await report.report_to_moderators(mock_bot, mock_reporter, mock_reported, mock_message)

            mock_bot.send_message.assert_called_once()
            call_args = mock_bot.send_message.call_args

            assert call_args[1]["chat_id"] == -1001234567890
            assert call_args[1]["parse_mode"] is None
            assert call_args[1].get("entities") is not None

            message_text = call_args[1]["text"]
            assert "This is a reported message" in message_text

    async def test_report_to_moderators_uses_entities_not_html(
        self, mock_bot, mock_reporter, mock_reported, mock_message
    ):
        """Test that report uses entities (not HTML parse_mode)."""
        mock_message.chat.title = "Chat"
        mock_message.chat.username = "chat"
        mock_message.chat.id = -100123
        mock_reporter.full_name = "Reporter"
        mock_reported.full_name = "Reported"

        with patch("app.application.services.report.settings") as mock_settings:
            mock_settings.admin.default_report_chat_id = -1001234567890

            await report.report_to_moderators(mock_bot, mock_reporter, mock_reported, mock_message)

            call_args = mock_bot.send_message.call_args
            # Must use parse_mode=None with entities
            assert call_args[1]["parse_mode"] is None


@pytest.mark.unit
class TestApplicationServiceIntegration:
    """Integration tests for application services."""

    async def test_buttons_and_report_services_independent(self):
        """Test that buttons and report services work independently."""
        # Test buttons service
        contacts_builder = await buttons.get_contacts_buttons()
        assert contacts_builder is not None

        # Test report service with mocks
        mock_bot = AsyncMock()
        mock_reporter = AsyncMock()
        mock_reporter.full_name = "Reporter"
        mock_reported = AsyncMock()
        mock_reported.full_name = "Reported"
        mock_message = AsyncMock()
        mock_message.text = "Test message"
        mock_message.chat.title = "Chat"
        mock_message.chat.username = "chat"
        mock_message.chat.id = -100123

        with patch("app.application.services.report.settings") as mock_settings:
            mock_settings.admin.default_report_chat_id = -1001234567890
            await report.report_to_moderators(mock_bot, mock_reporter, mock_reported, mock_message)

        # Both services should work without interference
        contacts_builder2 = await buttons.get_contacts_buttons()
        assert contacts_builder2 is not None
