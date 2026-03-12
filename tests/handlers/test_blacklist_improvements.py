"""Tests for blacklist command improvements."""

from unittest.mock import AsyncMock

import pytest
from app.application.services.user_service import UserService
from app.domain.entities import UserEntity
from app.presentation.telegram.handlers.moderation import show_blacklist

from tests.telegram_helpers import TelegramObjectFactory


@pytest.mark.handlers
class TestBlacklistImprovements:
    """Test cases for improved blacklist functionality."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def mock_user_service(self):
        return AsyncMock(spec=UserService)

    @pytest.fixture
    def sample_users(self):
        """Create sample blocked users for testing."""
        return [
            UserEntity(id=123, username="testuser", first_name="Test", last_name="User", is_blocked=True),
            UserEntity(id=456, username="spammer", first_name="Spam", is_blocked=True),
            UserEntity(id=789, username=None, first_name=None, last_name=None, is_blocked=True),
        ]

    async def test_blacklist_empty(self, telegram_factory: TelegramObjectFactory, mock_user_service: AsyncMock):
        """Test blacklist command when no blocked users exist."""
        # Arrange
        mock_user_service.get_blocked_users.return_value = []
        message = telegram_factory.create_message(text="/blacklist")

        # Act
        await show_blacklist(message, mock_user_service)

        # Assert
        mock_user_service.get_blocked_users.assert_called_once()
        message.answer.assert_called_once_with("Blacklist is empty")
        message.delete.assert_called_once()

    async def test_blacklist_with_users_pagination(
        self, telegram_factory: TelegramObjectFactory, mock_user_service: AsyncMock, sample_users: list[UserEntity]
    ):
        """Test blacklist command with blocked users and pagination."""
        # Arrange
        mock_user_service.get_blocked_users.return_value = sample_users
        message = telegram_factory.create_message(text="/blacklist")

        # Act
        await show_blacklist(message, mock_user_service)

        # Assert
        mock_user_service.get_blocked_users.assert_called_once()
        message.answer.assert_called_once()
        message.delete.assert_called_once()

    async def test_blacklist_find_user_by_username(
        self, telegram_factory: TelegramObjectFactory, mock_user_service: AsyncMock, sample_users: list[UserEntity]
    ):
        """Test blacklist command with username search."""
        # Arrange
        target_user = sample_users[0]  # testuser
        mock_user_service.find_blocked_user.return_value = target_user
        message = telegram_factory.create_message(text="/blacklist @testuser")

        # Act
        await show_blacklist(message, mock_user_service)

        # Assert
        mock_user_service.find_blocked_user.assert_called_once_with("@testuser")
        message.answer.assert_called_once()
        message.delete.assert_called_once()

    async def test_blacklist_find_user_by_id(
        self, telegram_factory: TelegramObjectFactory, mock_user_service: AsyncMock, sample_users: list[UserEntity]
    ):
        """Test blacklist command with user ID search."""
        # Arrange
        target_user = sample_users[1]  # spammer
        mock_user_service.find_blocked_user.return_value = target_user
        message = telegram_factory.create_message(text="/blacklist 456")

        # Act
        await show_blacklist(message, mock_user_service)

        # Assert
        mock_user_service.find_blocked_user.assert_called_once_with("456")
        message.answer.assert_called_once()
        message.delete.assert_called_once()

    async def test_blacklist_user_not_found(
        self, telegram_factory: TelegramObjectFactory, mock_user_service: AsyncMock
    ):
        """Test blacklist command when searched user is not found."""
        # Arrange
        mock_user_service.find_blocked_user.return_value = None
        message = telegram_factory.create_message(text="/blacklist @notfound")

        # Act
        await show_blacklist(message, mock_user_service)

        # Assert
        mock_user_service.find_blocked_user.assert_called_once_with("@notfound")
        message.answer.assert_called_once()
        message.delete.assert_called_once()

    async def test_blacklist_pagination_large_list(
        self, telegram_factory: TelegramObjectFactory, mock_user_service: AsyncMock
    ):
        """Test blacklist command shows pagination for large lists."""
        # Arrange - Create more than 10 users
        many_users = [UserEntity(id=i, username=f"user{i}", is_blocked=True) for i in range(15)]
        mock_user_service.get_blocked_users.return_value = many_users
        message = telegram_factory.create_message(text="/blacklist")

        # Act
        await show_blacklist(message, mock_user_service)

        # Assert
        mock_user_service.get_blocked_users.assert_called_once()
        message.answer.assert_called_once()
        message.delete.assert_called_once()
        # Verify pagination keyboard was attached
        assert message.answer.call_args[1].get("reply_markup") is not None
