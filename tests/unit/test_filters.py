"""Tests for telegram filters.

Only routing lives here now. The permission filters this module used to hold
were unreferenced duplicates of the admin middlewares and have been removed —
see tests/unit/test_admin_middleware.py for the checks that actually run.
"""

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

    @pytest.mark.parametrize(
        ("chat_type_filter", "actual_type", "expected"),
        [
            ("group", "group", True),
            ("group", "private", False),
            (["group", "supergroup"], "supergroup", True),
            (["group", "supergroup"], "private", False),
        ],
        ids=["single_match", "single_no_match", "multi_match", "multi_no_match"],
    )
    async def test_chat_type_matching(self, mock_message, chat_type_filter, actual_type, expected):
        """Test chat type matching for single and list filters."""
        filter_instance = ChatTypeFilter(chat_type_filter)
        mock_message.chat.type = actual_type

        result = await filter_instance(mock_message)

        assert result is expected

    async def test_empty_chat_types_list(self, mock_message):
        """Test empty chat types list."""
        filter_instance = ChatTypeFilter([])
        mock_message.chat.type = "group"

        result = await filter_instance(mock_message)

        assert result is False

    async def test_case_sensitive_matching(self, mock_message):
        """Test that chat type matching is case sensitive."""
        filter_instance = ChatTypeFilter("GROUP")  # Uppercase
        mock_message.chat.type = "group"  # Lowercase

        result = await filter_instance(mock_message)

        assert result is False
