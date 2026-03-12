"""Tests for telegram middlewares."""

from unittest.mock import AsyncMock

import pytest
from aiogram import types
from app.presentation.telegram.middlewares.chat_type import ChatTypeMiddleware


@pytest.mark.unit
class TestChatTypeMiddleware:
    """Test ChatTypeMiddleware."""

    @pytest.fixture
    def mock_handler(self):
        """Mock handler for middleware testing."""
        handler = AsyncMock()
        handler.return_value = "handler_result"
        return handler

    @pytest.fixture
    def mock_group_message(self):
        """Mock group message."""
        message = AsyncMock(spec=types.Message)
        message.chat = AsyncMock()
        message.chat.type = "group"
        return message

    @pytest.fixture
    def mock_supergroup_message(self):
        """Mock supergroup message."""
        message = AsyncMock(spec=types.Message)
        message.chat = AsyncMock()
        message.chat.type = "supergroup"
        return message

    @pytest.fixture
    def mock_private_message(self):
        """Mock private message."""
        message = AsyncMock(spec=types.Message)
        message.chat = AsyncMock()
        message.chat.type = "private"
        return message

    async def test_single_chat_type_match(self, mock_handler, mock_group_message):
        """Test middleware with single chat type that matches."""
        middleware = ChatTypeMiddleware("group")
        data = {}

        result = await middleware(mock_handler, mock_group_message, data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_group_message, data)

    async def test_single_chat_type_no_match(self, mock_handler, mock_private_message):
        """Test middleware with single chat type that doesn't match."""
        middleware = ChatTypeMiddleware("group")
        data = {}

        result = await middleware(mock_handler, mock_private_message, data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_multiple_chat_types_match(self, mock_handler, mock_supergroup_message):
        """Test middleware with multiple chat types that match."""
        middleware = ChatTypeMiddleware(["group", "supergroup"])
        data = {}

        result = await middleware(mock_handler, mock_supergroup_message, data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_supergroup_message, data)

    async def test_multiple_chat_types_no_match(self, mock_handler, mock_private_message):
        """Test middleware with multiple chat types that don't match."""
        middleware = ChatTypeMiddleware(["group", "supergroup"])
        data = {}

        result = await middleware(mock_handler, mock_private_message, data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_non_message_event(self, mock_handler):
        """Test middleware with non-message event."""
        middleware = ChatTypeMiddleware("group")
        callback_query = AsyncMock(spec=types.CallbackQuery)
        data = {}

        result = await middleware(mock_handler, callback_query, data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_empty_chat_types_list(self, mock_handler, mock_group_message):
        """Test middleware with empty chat types list."""
        middleware = ChatTypeMiddleware([])
        data = {}

        result = await middleware(mock_handler, mock_group_message, data)

        assert result is None
        mock_handler.assert_not_called()

    async def test_data_passed_through(self, mock_handler, mock_group_message):
        """Test that data is passed through to handler."""
        middleware = ChatTypeMiddleware("group")
        data = {"test_key": "test_value", "another_key": 123}

        result = await middleware(mock_handler, mock_group_message, data)

        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_group_message, data)

    async def test_handler_exception_propagated(self, mock_group_message):
        """Test that handler exceptions are propagated."""
        middleware = ChatTypeMiddleware("group")
        mock_handler = AsyncMock()
        mock_handler.side_effect = ValueError("Handler error")
        data = {}

        with pytest.raises(ValueError, match="Handler error"):
            await middleware(mock_handler, mock_group_message, data)

    async def test_case_sensitive_chat_type(self, mock_handler):
        """Test that chat type matching is case sensitive."""
        middleware = ChatTypeMiddleware("GROUP")  # Uppercase
        message = AsyncMock(spec=types.Message)
        message.chat = AsyncMock()
        message.chat.type = "group"  # Lowercase
        data = {}

        result = await middleware(mock_handler, message, data)

        assert result is None
        mock_handler.assert_not_called()

    @pytest.mark.parametrize("chat_type", ["private", "group", "supergroup"])
    async def test_middleware_with_all_chat_types(self, mock_handler, chat_type):
        """Test middleware configured for all common chat types accepts each type."""
        middleware = ChatTypeMiddleware(["private", "group", "supergroup", "channel"])
        data = {}

        msg = AsyncMock(spec=types.Message)
        msg.chat = AsyncMock()
        msg.chat.type = chat_type

        result = await middleware(mock_handler, msg, data)
        assert result == "handler_result"
        mock_handler.assert_called_once_with(msg, data)
