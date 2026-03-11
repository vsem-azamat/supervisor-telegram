"""Tests for BlacklistMiddleware."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import TelegramObject
from app.presentation.telegram.middlewares import black_list
from app.presentation.telegram.middlewares.black_list import BlacklistMiddleware

from tests.telegram_helpers import MockBot, TelegramObjectFactory, create_normal_user, create_test_chat


class MockHandler:
    """Mock handler for middleware testing."""

    def __init__(self):
        self.called = False
        self.call_args = None

    async def __call__(self, event: TelegramObject, data: dict[str, Any]) -> None:
        self.called = True
        self.call_args = (event, data)


@pytest.mark.middleware
class TestBlacklistMiddleware:
    """Test cases for BlacklistMiddleware."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def mock_user_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_bot(self):
        return MockBot()

    @pytest.fixture(autouse=True)
    def _clear_blacklist_cache(self):
        """Reset the blacklist cache before each test."""
        black_list._blacklist_cache = None

    @pytest.fixture
    def blacklist_middleware(self):
        return BlacklistMiddleware()

    @pytest.fixture
    def mock_handler(self):
        return MockHandler()

    async def test_blacklist_middleware_allows_non_blocked_user(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware allows non-blocked users to proceed."""
        # Arrange
        normal_user = create_normal_user()
        chat = create_test_chat()

        message = telegram_factory.create_message(user=normal_user, chat=chat, text="Hello world!")

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock no blocked users
        mock_user_repo.get_blocked_users.return_value = []

        # Act
        await blacklist_middleware(mock_handler, message, data)

        # Assert
        assert mock_handler.called is True
        mock_user_repo.get_blocked_users.assert_called_once()

    async def test_blacklist_middleware_blocks_blacklisted_user(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware blocks blacklisted users."""
        # Arrange
        blocked_user = create_normal_user(id=999, username="blocked_user")
        chat = create_test_chat()

        message = telegram_factory.create_message(
            user=blocked_user, chat=chat, text="I'm blocked but trying to send message"
        )

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock user is blocked
        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = blocked_user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        # Mock bot methods
        mock_bot.mock.ban_chat_member = AsyncMock()

        # Mock message delete method using patch
        with patch.object(message, "delete", new=AsyncMock()) as mock_delete:
            # Act
            result = await blacklist_middleware(mock_handler, message, data)

            # Assert
            assert result is None  # Should stop processing
            assert mock_handler.called is False  # Handler should not be called
            mock_bot.mock.ban_chat_member.assert_called_once_with(chat.id, blocked_user.id)
            mock_delete.assert_called_once()

    async def test_blacklist_middleware_handles_service_error(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware handles repository errors gracefully."""
        # Arrange
        user = create_normal_user()
        chat = create_test_chat()

        message = telegram_factory.create_message(user=user, chat=chat)

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock repository error
        mock_user_repo.get_blocked_users.side_effect = Exception("Database error")

        # Act - Should not raise exception
        with pytest.raises(Exception, match="Database error"):
            await blacklist_middleware(mock_handler, message, data)

    async def test_blacklist_middleware_missing_dependencies(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
    ):
        """Test middleware when dependencies are missing."""
        # Arrange
        user = create_normal_user()
        chat = create_test_chat()

        message = telegram_factory.create_message(user=user, chat=chat)

        data: dict[str, Any] = {}  # No dependencies

        # Act & Assert
        with pytest.raises(KeyError):
            await blacklist_middleware(mock_handler, message, data)

    async def test_blacklist_middleware_with_bot_messages(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware with bot messages."""
        # Arrange
        bot_user = create_normal_user(id=12345, is_bot=True)
        chat = create_test_chat()

        message = telegram_factory.create_message(user=bot_user, chat=chat, text="Bot message")

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock bot is in blocked list
        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = bot_user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        # Mock bot methods
        mock_bot.mock.ban_chat_member = AsyncMock()

        # Mock message delete method using patch
        with patch.object(message, "delete", new=AsyncMock()) as mock_delete:
            # Act
            result = await blacklist_middleware(mock_handler, message, data)

            # Assert - Should block bots too
            assert result is None
            mock_bot.mock.ban_chat_member.assert_called_once_with(chat.id, bot_user.id)
            mock_delete.assert_called_once()

    async def test_blacklist_middleware_performance_with_multiple_calls(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware performance with multiple concurrent calls."""
        # Arrange
        users = [create_normal_user(id=i) for i in range(100, 110)]
        chat = create_test_chat()

        messages = [telegram_factory.create_message(user=user, chat=chat) for user in users]

        mock_handlers = [MockHandler() for _ in messages]

        # Mock no blocked users
        mock_user_repo.get_blocked_users.return_value = []

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Act
        import asyncio

        tasks = [
            blacklist_middleware(handler, message, data)
            for handler, message in zip(mock_handlers, messages, strict=True)
        ]
        await asyncio.gather(*tasks)

        # Assert
        for handler in mock_handlers:
            assert handler.called is True

        # With TTL cache, get_blocked_users is called only once (cache serves subsequent calls)
        assert mock_user_repo.get_blocked_users.call_count == 1


@pytest.mark.middleware
class TestBlacklistMiddlewareEdgeCases:
    """Test edge cases for BlacklistMiddleware."""

    @pytest.fixture(autouse=True)
    def _clear_blacklist_cache(self):
        """Reset the blacklist cache before each test."""
        black_list._blacklist_cache = None

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def mock_user_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_bot(self):
        return MockBot()

    @pytest.fixture
    def blacklist_middleware(self):
        return BlacklistMiddleware()

    async def test_blacklist_middleware_with_callback_query(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware with callback query events."""
        # Arrange
        user = create_normal_user()

        callback_query = telegram_factory.create_callback_query(user=user)

        mock_handler = MockHandler()
        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        mock_user_repo.get_blocked_users.return_value = []

        # Act
        await blacklist_middleware(mock_handler, callback_query, data)

        # Assert - Should allow callback queries through (they're not Message events)
        assert mock_handler.called is True

    async def test_blacklist_middleware_with_chat_member_update(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware with chat member update events."""
        # Arrange
        user = create_normal_user()
        chat = create_test_chat()

        chat_member_update = telegram_factory.create_chat_member_updated(chat=chat, user=user)

        mock_handler = MockHandler()
        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock user is blocked
        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        # Act
        await blacklist_middleware(mock_handler, chat_member_update, data)

        # Assert - Should allow non-Message events through
        assert mock_handler.called is True

    async def test_blacklist_middleware_concurrent_same_user(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware with concurrent messages from same user."""
        # Arrange
        user = create_normal_user()
        chat = create_test_chat()

        # Create multiple messages from same user
        messages = [telegram_factory.create_message(user=user, chat=chat, text=f"Message {i}") for i in range(5)]

        mock_handlers = [MockHandler() for _ in messages]

        mock_user_repo.get_blocked_users.return_value = []

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Act
        import asyncio

        tasks = [
            blacklist_middleware(handler, message, data)
            for handler, message in zip(mock_handlers, messages, strict=True)
        ]
        await asyncio.gather(*tasks)

        # Assert
        for handler in mock_handlers:
            assert handler.called is True

        # With TTL cache, get_blocked_users is called only once (cache serves subsequent calls)
        assert mock_user_repo.get_blocked_users.call_count == 1

    async def test_blacklist_middleware_exception_handling(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware exception handling doesn't break the flow."""
        # Arrange
        user = create_normal_user()
        chat = create_test_chat()
        message = telegram_factory.create_message(user=user, chat=chat)

        # Create handler that raises exception
        async def failing_handler(event, data):
            raise ValueError("Handler failed")

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        mock_user_repo.get_blocked_users.return_value = []

        # Act & Assert
        with pytest.raises(ValueError, match="Handler failed"):
            await blacklist_middleware(failing_handler, message, data)
