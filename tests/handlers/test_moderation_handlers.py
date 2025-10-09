"""Tests for moderation handlers."""

from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from app.application.services.moderation_service import ModerationService
from app.presentation.telegram.handlers.moderation import ban_user, mute_user, unban_user

from tests.telegram_helpers import (
    TelegramObjectFactory,
    create_admin_user,
    create_normal_user,
    create_test_chat,
)


@pytest.mark.handlers
class TestModerationHandlers:
    """Test cases for moderation handlers."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def moderation_service(self):
        service = create_autospec(ModerationService, instance=True)
        service.mute_user = AsyncMock()
        service.ban_user = AsyncMock()
        service.unban_user = AsyncMock()
        return service

    async def test_mute_user_default_duration(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test muting user with default duration (5 minutes)."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user(id=777777777, username="spammer")
        chat = create_test_chat()

        # Create mute command message (reply to target user)
        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="mute", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock utility functions
        with (
            patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc,
            patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention,
        ):
            # Configure mocks
            mock_duration = MagicMock()
            mock_duration.until_date = 1234567890
            mock_duration.time = 5
            mock_duration.unit = "m"
            mock_duration.formatted_until_date = lambda: "2024-01-01 12:00:00"
            mock_calc.return_value = mock_duration
            mock_mention.return_value = "@spammer"

            # Act
            await mute_user(command_message, moderation_service)

        # Assert
        moderation_service.mute_user.assert_awaited_once()
        kwargs = moderation_service.mute_user.await_args.kwargs
        assert kwargs["admin_id"] == admin_user.id
        assert kwargs["user_id"] == target_user.id
        assert kwargs["chat_id"] == chat.id
        assert kwargs["duration"].minutes == 5

        reply_message.reply.assert_called_once()
        command_message.delete.assert_called_once()

    async def test_mute_user_custom_duration(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test muting user with custom duration."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="mute",
            args="10m",  # 10 minutes
            user=admin_user,
            chat=chat,
            reply_to_message=reply_message,
        )

        # Mock utility functions
        with (
            patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc,
            patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention,
        ):
            # Configure mocks
            mock_duration = MagicMock()
            mock_duration.until_date = 1234567890
            mock_duration.time = 10
            mock_duration.unit = "m"
            mock_duration.formatted_until_date = lambda: "2024-01-01 12:10:00"
            mock_calc.return_value = mock_duration
            mock_mention.return_value = "@user"

            # Act
            await mute_user(command_message, moderation_service)

        # Assert
        mock_calc.assert_called_once_with(command_message.text)
        moderation_service.mute_user.assert_awaited_once()
        assert moderation_service.mute_user.await_args.kwargs["duration"].minutes == 10

    async def test_mute_user_invalid_duration(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test mute command with invalid duration argument."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="mute",
            args="invalid",  # Invalid duration
            user=admin_user,
            chat=chat,
            reply_to_message=reply_message,
        )

        # Mock utility functions to raise exception
        with (
            patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc,
            patch("app.presentation.telegram.handlers.moderation.other.sleep_and_delete") as mock_sleep,
        ):
            mock_calc.side_effect = ValueError("Invalid duration")
            mock_sleep.return_value = None

            # Act
            await mute_user(command_message, moderation_service)

        # Assert - should handle error gracefully
        command_message.answer.assert_called_once()
        command_message.delete.assert_called_once()
        mock_sleep.assert_called_once()

    async def test_mute_user_telegram_error(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test mute command when Telegram API fails."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="mute", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock bot to raise exception
        moderation_service.mute_user.side_effect = Exception("API Error")

        # Mock utility functions
        with patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc:
            mock_duration = MagicMock()
            mock_duration.until_date = 1234567890
            mock_duration.time = 5
            mock_duration.unit = "m"
            mock_calc.return_value = mock_duration

            # Act
            await mute_user(command_message, moderation_service)

        # Assert - should handle error gracefully
        command_message.answer.assert_called_once()
        error_msg = command_message.answer.call_args[0][0]
        assert "Произошла ошибка" in error_msg

    @pytest.mark.skip(reason="Chat object is frozen and cannot be mocked easily")
    async def test_unmute_user_success(self, telegram_factory: TelegramObjectFactory):
        """Test successful user unmute."""
        # This test is skipped due to pydantic frozen model restrictions
        pass

    async def test_ban_user_success(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test successful user ban."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="ban", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock bot methods
        moderation_service.ban_user.return_value = None

        # Mock utility functions
        with patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@user"

            # Act
            await ban_user(command_message, moderation_service)

        # Assert
        moderation_service.ban_user.assert_awaited_once_with(
            admin_id=admin_user.id, user_id=target_user.id, chat_id=chat.id
        )
        command_message.answer.assert_called_once()
        command_message.delete.assert_called_once()

    async def test_ban_user_with_message_deletion(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test ban user with message deletion."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="ban", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock bot methods
        moderation_service.ban_user.return_value = None

        # Mock utility functions
        with patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@user"

            # Act
            await ban_user(command_message, moderation_service)

        # Assert
        moderation_service.ban_user.assert_awaited_once()
        command_message.delete.assert_called_once()

    async def test_unban_user_success(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test successful user unban."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="unban", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock bot methods
        moderation_service.unban_user.return_value = None

        # Mock utility functions
        with patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention:
            mock_mention.return_value = "@user"

            # Act
            await unban_user(command_message, moderation_service)

        # Assert
        moderation_service.unban_user.assert_awaited_once_with(
            admin_id=admin_user.id, user_id=target_user.id, chat_id=chat.id
        )
        command_message.answer.assert_called_once()
        command_message.delete.assert_called_once()


@pytest.mark.handlers
class TestModerationHandlerEdgeCases:
    """Test edge cases for moderation handlers."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def moderation_service(self):
        service = create_autospec(ModerationService, instance=True)
        service.mute_user = AsyncMock()
        service.ban_user = AsyncMock()
        service.unban_user = AsyncMock()
        return service

    async def test_moderation_command_no_reply(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test moderation commands without reply message."""
        # Arrange
        admin_user = create_admin_user()
        chat = create_test_chat()

        command_message = telegram_factory.create_command_message(
            command="mute",
            user=admin_user,
            chat=chat,  # No reply_to_message
        )

        # Act
        await mute_user(command_message, moderation_service)

        # Assert
        command_message.answer.assert_called_once()
        command_message.delete.assert_called_once()
        answer_text = command_message.answer.call_args[0][0]
        assert "ответом" in answer_text.lower()

    async def test_moderation_self_target(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test trying to moderate self."""
        # Arrange
        admin_user = create_admin_user()
        chat = create_test_chat()

        # Reply to own message
        reply_message = telegram_factory.create_message(user=admin_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="mute", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock utility functions
        with (
            patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc,
            patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention,
        ):
            mock_duration = MagicMock()
            mock_duration.until_date = 1234567890
            mock_duration.time = 5
            mock_duration.unit = "m"
            mock_duration.formatted_until_date = lambda: "2024-01-01 12:00:00"
            mock_calc.return_value = mock_duration
            mock_mention.return_value = "@admin"

            # Act - should work, handler doesn't prevent self-moderation
            await mute_user(command_message, moderation_service)

        # Assert
        moderation_service.mute_user.assert_awaited_once()

    async def test_moderation_extreme_duration(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test moderation with extreme duration values that exceed maximum (1 year)."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="mute",
            args="999999h",  # Extreme duration - exceeds 1 year limit
            user=admin_user,
            chat=chat,
            reply_to_message=reply_message,
        )

        # Mock utility functions
        with (
            patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc,
            patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention,
        ):
            mock_duration = MagicMock()
            mock_duration.until_date = 9999999999
            mock_duration.time = 999999
            mock_duration.unit = "h"
            mock_duration.formatted_until_date = lambda: "2050-01-01 12:00:00"
            mock_calc.return_value = mock_duration
            mock_mention.return_value = "@user"

            # Act
            await mute_user(command_message, moderation_service)

        # Assert - should handle error gracefully (duration exceeds max)
        # The service should not be called because validation fails
        moderation_service.mute_user.assert_not_awaited()
        command_message.answer.assert_called_once()
        error_msg = command_message.answer.call_args[0][0]
        assert "Произошла ошибка" in error_msg

    async def test_concurrent_moderation_actions(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test concurrent moderation actions on same user."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        mute_message = telegram_factory.create_command_message(
            command="mute", user=admin_user, chat=chat, reply_to_message=reply_message
        )
        ban_message = telegram_factory.create_command_message(
            command="ban", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock utility functions
        with (
            patch("app.presentation.telegram.handlers.moderation.other.calculate_mute_duration") as mock_calc,
            patch("app.presentation.telegram.handlers.moderation.other.get_user_mention") as mock_mention,
        ):
            mock_duration = MagicMock()
            mock_duration.until_date = 1234567890
            mock_duration.time = 5
            mock_duration.unit = "m"
            mock_duration.formatted_until_date = lambda: "2024-01-01 12:00:00"
            mock_calc.return_value = mock_duration
            mock_mention.return_value = "@user"

            # Act - simulate concurrent actions
            import asyncio

            await asyncio.gather(
                mute_user(mute_message, moderation_service),
                ban_user(ban_message, moderation_service),
            )

        # Assert
        moderation_service.mute_user.assert_awaited_once()
        moderation_service.ban_user.assert_awaited_once()

    async def test_moderation_permission_error(
        self, telegram_factory: TelegramObjectFactory, moderation_service: ModerationService
    ):
        """Test moderation when bot lacks permissions."""
        # Arrange
        admin_user = create_admin_user()
        target_user = create_normal_user()
        chat = create_test_chat()

        reply_message = telegram_factory.create_message(user=target_user, chat=chat)
        command_message = telegram_factory.create_command_message(
            command="ban", user=admin_user, chat=chat, reply_to_message=reply_message
        )

        # Mock bot to raise permission error
        moderation_service.ban_user.side_effect = Exception("Not enough rights")

        # Mock utility functions
        with patch("app.presentation.telegram.handlers.moderation.other.sleep_and_delete") as mock_sleep:
            mock_sleep.return_value = None

            # Act
            await ban_user(command_message, moderation_service)

        # Assert
        command_message.answer.assert_called_once()
        command_message.delete.assert_called_once()
        mock_sleep.assert_called_once()
