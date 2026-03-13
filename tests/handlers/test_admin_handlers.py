"""Tests for admin handlers."""

from unittest.mock import AsyncMock, patch

import pytest
from app.infrastructure.db.repositories.admin import AdminRepository
from app.presentation.telegram.handlers.admin import delete_admin, new_admin

from tests.telegram_helpers import (
    TelegramObjectFactory,
    create_admin_user,
    create_normal_user,
    create_test_chat,
)


@pytest.fixture
def telegram_factory():
    return TelegramObjectFactory()


@pytest.fixture
def mock_admin_repository():
    return AsyncMock(spec=AdminRepository)


@pytest.mark.handlers
class TestAdminHandlers:
    """Test cases for admin management handlers."""

    async def test_new_admin_success(self, telegram_factory: TelegramObjectFactory, mock_admin_repository: AsyncMock):
        """Test successfully adding a new admin."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user(id=777777777, username="new_admin")
        chat = create_test_chat()

        # Create message that replies to target user
        reply_message = telegram_factory.create_message(user=target_user, chat=chat, text="I want to be admin")

        command_message = telegram_factory.create_command_message(
            command="admin", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock repository responses
        mock_admin_repository.is_admin.return_value = False
        mock_admin_repository.insert_admin.return_value = None

        # Act
        with patch("app.presentation.telegram.utils.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@new_admin"

            await new_admin(command_message, mock_admin_repository)

        # Assert
        mock_admin_repository.is_admin.assert_called_once_with(target_user.id)
        mock_admin_repository.insert_admin.assert_called_once_with(target_user.id)
        command_message.answer.assert_called_once()
        command_message.delete.assert_called_once()

        # Verify success message
        call_args = command_message.answer.call_args[0][0]
        assert "добавлен" in call_args
        assert "✅" in call_args

    async def test_new_admin_already_exists(
        self, telegram_factory: TelegramObjectFactory, mock_admin_repository: AsyncMock
    ):
        """Test adding admin who is already an admin."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user(id=777777777, username="existing_admin")
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)

        command_message = telegram_factory.create_command_message(
            command="admin", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock repository - user is already admin
        mock_admin_repository.is_admin.return_value = True

        # Act
        with patch("app.presentation.telegram.utils.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@existing_admin"

            await new_admin(command_message, mock_admin_repository)

        # Assert
        mock_admin_repository.is_admin.assert_called_once_with(target_user.id)
        mock_admin_repository.insert_admin.assert_not_called()  # Should not try to insert

        # Verify "already exists" message
        call_args = command_message.answer.call_args[0][0]
        assert "уже есть в базе" in call_args

    async def test_new_admin_no_reply(self, telegram_factory: TelegramObjectFactory, mock_admin_repository: AsyncMock):
        """Test admin command without replying to a message."""
        # Arrange
        admin_user = create_admin_user()
        chat = create_test_chat()

        command_message = telegram_factory.create_command_message(
            command="admin",
            user=admin_user,
            chat=chat,
            reply_to_message=None,  # No reply
        )

        # Act - Should handle gracefully and respond with error message
        await new_admin(command_message, mock_admin_repository)

        # Assert - Should send error message and not call repository methods
        command_message.answer.assert_called_once()
        error_msg = command_message.answer.call_args[0][0]
        assert "ответ на сообщение" in error_msg.lower()

        # Repository methods should not be called
        mock_admin_repository.is_admin.assert_not_called()
        mock_admin_repository.insert_admin.assert_not_called()

    async def test_delete_admin_success(
        self, telegram_factory: TelegramObjectFactory, mock_admin_repository: AsyncMock
    ):
        """Test successfully removing an admin."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user(id=777777777, username="admin_to_remove")
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)

        command_message = telegram_factory.create_command_message(
            command="unadmin", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock repository - user is currently admin
        mock_admin_repository.is_admin.return_value = True
        mock_admin_repository.delete_admin.return_value = None

        # Act
        with patch("app.presentation.telegram.utils.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@admin_to_remove"

            await delete_admin(command_message, mock_admin_repository)

        # Assert
        mock_admin_repository.is_admin.assert_called_once_with(target_user.id)
        mock_admin_repository.delete_admin.assert_called_once_with(target_user.id)

        # Verify success message
        call_args = command_message.answer.call_args[0][0]
        assert "удален" in call_args
        assert "❌" in call_args

    async def test_delete_admin_not_admin(
        self, telegram_factory: TelegramObjectFactory, mock_admin_repository: AsyncMock
    ):
        """Test removing admin from user who is not an admin."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user(id=777777777, username="not_admin")
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)

        command_message = telegram_factory.create_command_message(
            command="unadmin", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock repository - user is not admin
        mock_admin_repository.is_admin.return_value = False

        # Act
        with patch("app.presentation.telegram.utils.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@not_admin"

            await delete_admin(command_message, mock_admin_repository)

        # Assert
        mock_admin_repository.is_admin.assert_called_once_with(target_user.id)
        mock_admin_repository.delete_admin.assert_not_called()  # Should not try to delete

        # Verify "not admin" message
        call_args = command_message.answer.call_args[0][0]
        assert "не является админом" in call_args


@pytest.mark.handlers
class TestAdminHandlerEdgeCases:
    """Test edge cases and error conditions for admin handlers."""

    async def test_admin_command_database_error(
        self, telegram_factory: TelegramObjectFactory, mock_admin_repository: AsyncMock
    ):
        """Test admin command when database operation fails."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="admin", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock database error
        mock_admin_repository.is_admin.side_effect = Exception("Database connection failed")

        # Act & Assert
        with pytest.raises(Exception, match="Database connection failed"):
            await new_admin(command_message, mock_admin_repository)
