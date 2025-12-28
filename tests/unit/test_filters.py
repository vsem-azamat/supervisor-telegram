"""Tests for telegram filters."""

from unittest.mock import AsyncMock

import pytest
from aiogram import types
from app.presentation.telegram.utils.filters import ChatTypeFilter


@pytest.mark.unit
class TestChatTypeFilter:
    """Test ChatTypeFilter."""

    @pytest.fixture
    def mock_message(self):
        message = AsyncMock(spec=types.Message)
        message.chat = AsyncMock()
        return message

    async def test_single_chat_type_match(self, mock_message):
        """Test single chat type that matches."""
        # Arrange
        filter_instance = ChatTypeFilter("group")
        mock_message.chat.type = "group"

        # Act
        result = await filter_instance(mock_message)

        # Assert
        assert result is True

    async def test_single_chat_type_no_match(self, mock_message):
        """Test single chat type that doesn't match."""
        # Arrange
        filter_instance = ChatTypeFilter("group")
        mock_message.chat.type = "private"

        # Act
        result = await filter_instance(mock_message)

        # Assert
        assert result is False

    async def test_multiple_chat_types_match(self, mock_message):
        """Test multiple chat types with match."""
        # Arrange
        filter_instance = ChatTypeFilter(["group", "supergroup"])
        mock_message.chat.type = "supergroup"

        # Act
        result = await filter_instance(mock_message)

        # Assert
        assert result is True

    async def test_multiple_chat_types_no_match(self, mock_message):
        """Test multiple chat types with no match."""
        # Arrange
        filter_instance = ChatTypeFilter(["group", "supergroup"])
        mock_message.chat.type = "private"

        # Act
        result = await filter_instance(mock_message)

        # Assert
        assert result is False

    async def test_empty_chat_types_list(self, mock_message):
        """Test empty chat types list."""
        # Arrange
        filter_instance = ChatTypeFilter([])
        mock_message.chat.type = "group"

        # Act
        result = await filter_instance(mock_message)

        # Assert
        assert result is False

    def test_filter_initialization_string(self):
        """Test filter initialization with string."""
        filter_instance = ChatTypeFilter("private")
        assert filter_instance.chat_type == "private"

    def test_filter_initialization_list(self):
        """Test filter initialization with list."""
        chat_types = ["group", "supergroup"]
        filter_instance = ChatTypeFilter(chat_types)
        assert filter_instance.chat_type == chat_types

    async def test_case_sensitive_matching(self, mock_message):
        """Test that chat type matching is case sensitive."""
        # Arrange
        filter_instance = ChatTypeFilter("GROUP")  # Uppercase
        mock_message.chat.type = "group"  # Lowercase

        # Act
        result = await filter_instance(mock_message)

        # Assert
        assert result is False
