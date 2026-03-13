"""Tests for buttons service."""

from unittest.mock import AsyncMock, patch

import pytest
from app.presentation.telegram.utils import buttons


@pytest.mark.unit
class TestButtonsService:
    """Test buttons service."""

    async def test_get_contacts_buttons(self):
        """Test getting contacts buttons."""
        builder = await buttons.get_contacts_buttons()

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
        mock_db = AsyncMock()

        with patch("app.presentation.telegram.utils.buttons.ChatLinkRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_chat_links.return_value = []
            mock_repo_class.return_value = mock_repo

            builder = await buttons.get_chat_buttons(mock_db)

            keyboard = builder.as_markup()
            assert len(keyboard.inline_keyboard) == 0

    async def test_get_chat_buttons_with_chats(self):
        """Test getting chat buttons with existing chats."""
        mock_db = AsyncMock()
        mock_chat1 = AsyncMock()
        mock_chat1.text = "Chat 1"
        mock_chat1.link = "https://t.me/chat1"

        mock_chat2 = AsyncMock()
        mock_chat2.text = "Chat 2"
        mock_chat2.link = "https://t.me/chat2"

        with patch("app.presentation.telegram.utils.buttons.ChatLinkRepository") as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.get_chat_links.return_value = [mock_chat1, mock_chat2]
            mock_repo_class.return_value = mock_repo

            builder = await buttons.get_chat_buttons(mock_db)

            keyboard = builder.as_markup()
            assert len(keyboard.inline_keyboard) == 1  # One row with 2 buttons (adjust(2))
            assert len(keyboard.inline_keyboard[0]) == 2  # Two buttons in the row

            button1 = keyboard.inline_keyboard[0][0]
            assert button1.text == "Chat 1"
            assert button1.url == "https://t.me/chat1"

            button2 = keyboard.inline_keyboard[0][1]
            assert button2.text == "Chat 2"
            assert button2.url == "https://t.me/chat2"
