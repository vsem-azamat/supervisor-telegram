"""Unit tests for ModerationService."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import BanChatMember, DeleteMessage, RestrictChatMember
from aiogram.types import ChatPermissions
from app.application.services.moderation_service import ModerationService
from app.application.services.spam import SpamService
from app.domain.exceptions import TelegramApiException
from app.domain.repositories import IChatRepository, IMessageRepository, IUserRepository
from app.domain.value_objects import MuteDuration

from tests.factories import ChatFactory, MessageFactory


class TestModerationService:
    """Test cases for ModerationService."""

    @pytest.fixture
    def mock_bot(self) -> AsyncMock:
        """Create a mock bot."""
        return AsyncMock()

    @pytest.fixture
    def mock_chat_repository(self) -> AsyncMock:
        """Create a mock chat repository."""
        return AsyncMock(spec=IChatRepository)

    @pytest.fixture
    def mock_message_repository(self) -> AsyncMock:
        """Create a mock message repository."""
        return AsyncMock(spec=IMessageRepository)

    @pytest.fixture
    def mock_user_repository(self) -> AsyncMock:
        """Create a mock user repository."""
        return AsyncMock(spec=IUserRepository)

    @pytest.fixture
    def mock_spam_service(self) -> MagicMock:
        """Create a mock spam service."""
        mock_service = MagicMock(spec=SpamService)
        mock_service.detect = AsyncMock(return_value=False)
        return mock_service

    @pytest.fixture
    def moderation_service(
        self,
        mock_bot: AsyncMock,
        mock_chat_repository: AsyncMock,
        mock_message_repository: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_spam_service: AsyncMock,
    ) -> ModerationService:
        """Create ModerationService with mocked dependencies."""
        return ModerationService(
            mock_bot,
            mock_chat_repository,
            mock_message_repository,
            mock_user_repository,
            mock_spam_service,
        )

    @pytest.mark.asyncio
    async def test_mute_user_success(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test successfully muting a user."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        chat_id = -1001234567890
        duration = MuteDuration(minutes=5)
        reason = "Spam"

        mock_bot.restrict_chat_member.return_value = None

        # Act
        with patch.object(moderation_service, "logger") as mock_logger:
            await moderation_service.mute_user(
                admin_id=admin_id, user_id=user_id, chat_id=chat_id, duration=duration, reason=reason
            )

        # Assert
        mock_bot.restrict_chat_member.assert_called_once()
        call_args = mock_bot.restrict_chat_member.call_args
        assert call_args[1]["chat_id"] == chat_id
        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["permissions"] is not None
        assert call_args[1]["permissions"].can_send_messages is False
        assert "until_date" in call_args[1]

        mock_logger.log_moderation_action.assert_called_once_with(
            admin_id=admin_id, target_user_id=user_id, action="mute", chat_id=chat_id, reason=reason, duration="5m"
        )

    @pytest.mark.asyncio
    async def test_mute_user_telegram_error(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test muting user with Telegram API error."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        chat_id = -1001234567890
        duration = MuteDuration(minutes=5)

        telegram_error = TelegramBadRequest(
            method=RestrictChatMember(chat_id=chat_id, user_id=user_id, permissions=ChatPermissions()),
            message="User not found",
        )
        mock_bot.restrict_chat_member.side_effect = telegram_error

        # Act & Assert
        with patch.object(moderation_service, "logger") as mock_logger:
            with pytest.raises(TelegramApiException) as exc_info:
                await moderation_service.mute_user(
                    admin_id=admin_id, user_id=user_id, chat_id=chat_id, duration=duration
                )

        assert exc_info.value.operation == "mute_user"
        mock_logger.log_telegram_error.assert_called_once_with(
            operation="mute_user",
            error="Telegram server says - User not found",
            chat_id=chat_id,
            user_id=user_id,
        )

    @pytest.mark.asyncio
    async def test_unmute_user_success(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test successfully unmuting a user."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        chat_id = -1001234567890
        reason = "Appealed"

        mock_bot.restrict_chat_member.return_value = None

        # Act
        with patch.object(moderation_service, "logger") as mock_logger:
            await moderation_service.unmute_user(admin_id=admin_id, user_id=user_id, chat_id=chat_id, reason=reason)

        # Assert
        mock_bot.restrict_chat_member.assert_called_once()
        call_args = mock_bot.restrict_chat_member.call_args
        assert call_args[1]["chat_id"] == chat_id
        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["permissions"] is not None
        assert call_args[1]["permissions"].can_send_messages is True  # Should restore permissions

        mock_logger.log_moderation_action.assert_called_once_with(
            admin_id=admin_id, target_user_id=user_id, action="unmute", chat_id=chat_id, reason=reason
        )

    @pytest.mark.asyncio
    async def test_ban_user_success(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test successfully banning a user."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        chat_id = -1001234567890
        reason = "Repeated violations"

        mock_bot.ban_chat_member.return_value = None

        # Act
        with patch.object(moderation_service, "logger") as mock_logger:
            await moderation_service.ban_user(admin_id=admin_id, user_id=user_id, chat_id=chat_id, reason=reason)

        # Assert
        mock_bot.ban_chat_member.assert_called_once_with(chat_id=chat_id, user_id=user_id)

        mock_logger.log_moderation_action.assert_called_once_with(
            admin_id=admin_id, target_user_id=user_id, action="ban", chat_id=chat_id, reason=reason
        )

    @pytest.mark.asyncio
    async def test_unban_user_success(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test successfully unbanning a user."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        chat_id = -1001234567890
        reason = "Appeal approved"

        mock_bot.unban_chat_member.return_value = None

        # Act
        with patch.object(moderation_service, "logger") as mock_logger:
            await moderation_service.unban_user(admin_id=admin_id, user_id=user_id, chat_id=chat_id, reason=reason)

        # Assert
        mock_bot.unban_chat_member.assert_called_once_with(chat_id=chat_id, user_id=user_id)

        mock_logger.log_moderation_action.assert_called_once_with(
            admin_id=admin_id, target_user_id=user_id, action="unban", chat_id=chat_id, reason=reason
        )

    @pytest.mark.asyncio
    async def test_ban_user_globally_success(
        self, moderation_service: ModerationService, mock_bot: AsyncMock, mock_chat_repository: AsyncMock
    ):
        """Test successfully banning user globally across all chats."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        reason = "Global spam"

        chats = ChatFactory.create_batch(3)
        mock_chat_repository.get_all.return_value = chats
        mock_bot.ban_chat_member.return_value = None

        # Act
        with patch.object(moderation_service, "logger") as mock_logger:
            await moderation_service.ban_user_globally(admin_id=admin_id, user_id=user_id, reason=reason)

        # Assert
        assert mock_bot.ban_chat_member.call_count == 3

        # Verify each chat had ban called
        for i, chat in enumerate(chats):
            call = mock_bot.ban_chat_member.call_args_list[i]
            assert call[1]["chat_id"] == chat.id
            assert call[1]["user_id"] == user_id

        # Verify logging happened for each chat
        assert mock_logger.log_moderation_action.call_count == 3

    @pytest.mark.asyncio
    async def test_ban_user_globally_partial_failure(
        self, moderation_service: ModerationService, mock_bot: AsyncMock, mock_chat_repository: AsyncMock
    ):
        """Test global ban with some failures."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789

        chats = ChatFactory.create_batch(3)
        mock_chat_repository.get_all.return_value = chats

        # Mock bot to fail on second chat
        def ban_side_effect(chat_id, user_id, **kwargs):
            if chat_id == chats[1].id:
                raise TelegramBadRequest(
                    method=BanChatMember(chat_id=chat_id, user_id=user_id), message="User is admin"
                )
            return

        mock_bot.ban_chat_member.side_effect = ban_side_effect

        # Act
        with patch.object(moderation_service, "logger") as mock_logger, pytest.raises(TelegramApiException):
            await moderation_service.ban_user_globally(admin_id=admin_id, user_id=user_id)

        # Assert
        assert mock_bot.ban_chat_member.call_count == 2  # Should stop at failure
        mock_logger.log_telegram_error.assert_called_once()  # Error should be logged

    @pytest.mark.asyncio
    async def test_unban_user_globally_success(
        self, moderation_service: ModerationService, mock_bot: AsyncMock, mock_chat_repository: AsyncMock
    ):
        """Test successfully unbanning user globally."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        reason = "Global appeal"

        chats = ChatFactory.create_batch(2)
        mock_chat_repository.get_all.return_value = chats
        mock_bot.unban_chat_member.return_value = None

        # Act
        with patch.object(moderation_service, "logger") as mock_logger:
            await moderation_service.unban_user_globally(admin_id=admin_id, user_id=user_id, reason=reason)

        # Assert
        assert mock_bot.unban_chat_member.call_count == 2

        # Verify logging happened for each chat
        assert mock_logger.log_moderation_action.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_message_success(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test successfully deleting a message."""
        # Arrange
        chat_id = -1001234567890
        message_id = 42

        mock_bot.delete_message.return_value = None

        # Act
        with patch("app.application.services.moderation_service.BotLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger_class.return_value = mock_logger

            await moderation_service.delete_message(chat_id=chat_id, message_id=message_id)

        # Assert
        mock_bot.delete_message.assert_called_once_with(chat_id, message_id)

    @pytest.mark.asyncio
    async def test_delete_message_telegram_error(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test deleting message with Telegram API error."""
        # Arrange
        chat_id = -1001234567890
        message_id = 42

        telegram_error = TelegramBadRequest(
            method=DeleteMessage(chat_id=chat_id, message_id=message_id), message="Message too old"
        )
        mock_bot.delete_message.side_effect = telegram_error

        # Act & Assert
        with patch.object(moderation_service, "logger") as mock_logger:
            with pytest.raises(TelegramApiException) as exc_info:
                await moderation_service.delete_message(chat_id=chat_id, message_id=message_id)

        assert exc_info.value.operation == "delete_message"
        mock_logger.log_telegram_error.assert_called_once_with(
            operation="delete_message",
            error="Telegram server says - Message too old",
            chat_id=chat_id,
        )

    @pytest.mark.asyncio
    async def test_delete_user_messages_success(
        self, moderation_service: ModerationService, mock_bot: AsyncMock, mock_message_repository: AsyncMock
    ):
        """Test successfully deleting user messages."""
        # Arrange
        user_id = 123456789
        chat_id = -1001234567890

        messages = MessageFactory.create_batch(3, user_id=user_id, chat_id=chat_id)
        mock_message_repository.get_user_messages.return_value = messages
        mock_bot.delete_message.return_value = None

        # Act
        await moderation_service._delete_user_messages(user_id, chat_id)

        # Assert
        assert mock_bot.delete_message.call_count == 3
        mock_message_repository.get_user_messages.assert_called_once_with(user_id, chat_id)

    @pytest.mark.asyncio
    async def test_delete_user_messages_partial_failure(
        self, moderation_service: ModerationService, mock_bot: AsyncMock, mock_message_repository: AsyncMock
    ):
        """Test deleting user messages with partial failures."""
        # Arrange
        user_id = 123456789
        chat_id = -1001234567890

        messages = MessageFactory.create_batch(3, user_id=user_id, chat_id=chat_id)
        mock_message_repository.get_user_messages.return_value = messages

        # Mock bot to fail on second message
        def delete_side_effect(chat_id, message_id):
            if message_id == messages[1].message_id:
                raise TelegramBadRequest(
                    method=DeleteMessage(chat_id=chat_id, message_id=message_id), message="Message too old"
                )
            return

        mock_bot.delete_message.side_effect = delete_side_effect

        # Act & Assert
        with pytest.raises(TelegramApiException):
            await moderation_service._delete_user_messages(user_id, chat_id)

        # Assert
        assert mock_bot.delete_message.call_count == 2  # Should stop at failure

    @pytest.mark.asyncio
    async def test_build_blacklist_preview(
        self,
        moderation_service: ModerationService,
        mock_message_repository: AsyncMock,
        mock_spam_service: MagicMock,
    ):
        """Preview should aggregate counts and spam detection."""
        mock_message_repository.count_user_chats.return_value = 3
        mock_message_repository.count_user_messages.return_value = 12
        mock_spam_service.detect.return_value = True

        preview = await moderation_service.build_blacklist_preview(user_id=1, chat_id=2, message_text="test")

        assert preview.chats_count == 3
        assert preview.messages_count == 12
        assert preview.spam_detected is True
        mock_message_repository.count_user_chats.assert_awaited_once_with(1)
        mock_message_repository.count_user_messages.assert_awaited_once_with(1)
        mock_spam_service.detect.assert_awaited_once_with(chat_id=2, user_id=1, text="test")

    @pytest.mark.asyncio
    async def test_blacklist_user_marks_and_bans(
        self,
        moderation_service: ModerationService,
        mock_bot: AsyncMock,
        mock_chat_repository: AsyncMock,
        mock_message_repository: AsyncMock,
        mock_user_repository: AsyncMock,
    ):
        """Blacklisting should flag user, ban across chats, and remove history when requested."""
        user_id = 123
        chats = ChatFactory.create_batch(2)
        mock_chat_repository.get_all.return_value = chats
        mock_message_repository.get_user_messages.return_value = [
            MessageFactory.create(user_id=user_id, chat_id=chat.id, message_id=10) for chat in chats
        ]

        await moderation_service.blacklist_user(
            user_id=user_id,
            source_chat_id=chats[0].id,
            source_message_id=42,
            revoke_messages=True,
            mark_spam=True,
        )

        mock_user_repository.add_to_blacklist.assert_awaited_once_with(user_id)
        mock_message_repository.label_spam.assert_awaited_once_with(chat_id=chats[0].id, message_id=42)
        assert mock_bot.ban_chat_member.await_count == len(chats)
        assert mock_message_repository.get_user_messages.await_count == 1
        assert mock_bot.delete_message.await_count >= len(chats)  # source message + revoked history

    @pytest.mark.asyncio
    async def test_remove_from_blacklist_unbans_all(
        self,
        moderation_service: ModerationService,
        mock_bot: AsyncMock,
        mock_chat_repository: AsyncMock,
        mock_user_repository: AsyncMock,
    ):
        """Removing from blacklist should unban user everywhere."""
        user_id = 321
        chats = ChatFactory.create_batch(2)
        mock_chat_repository.get_all.return_value = chats

        await moderation_service.remove_from_blacklist(user_id)

        mock_user_repository.remove_from_blacklist.assert_awaited_once_with(user_id)
        assert mock_bot.unban_chat_member.await_count == len(chats)


@pytest.mark.unit
class TestModerationServiceEdgeCases:
    """Test edge cases and error conditions for ModerationService."""

    @pytest.fixture
    def mock_bot(self) -> AsyncMock:
        """Create a mock bot."""
        return AsyncMock()

    @pytest.fixture
    def mock_chat_repository(self) -> AsyncMock:
        """Create a mock chat repository."""
        return AsyncMock(spec=IChatRepository)

    @pytest.fixture
    def mock_message_repository(self) -> AsyncMock:
        """Create a mock message repository."""
        return AsyncMock(spec=IMessageRepository)

    @pytest.fixture
    def mock_user_repository(self) -> AsyncMock:
        """Create a mock user repository."""
        return AsyncMock(spec=IUserRepository)

    @pytest.fixture
    def mock_spam_service(self) -> MagicMock:
        """Create a mock spam service."""
        mock_service = MagicMock(spec=SpamService)
        mock_service.detect = AsyncMock(return_value=False)
        return mock_service

    @pytest.fixture
    def moderation_service(
        self,
        mock_bot: AsyncMock,
        mock_chat_repository: AsyncMock,
        mock_message_repository: AsyncMock,
        mock_user_repository: AsyncMock,
        mock_spam_service: MagicMock,
    ) -> ModerationService:
        """Create ModerationService with mocked dependencies."""
        return ModerationService(
            mock_bot,
            mock_chat_repository,
            mock_message_repository,
            mock_user_repository,
            mock_spam_service,
        )

    @pytest.mark.asyncio
    async def test_global_ban_no_chats(
        self, moderation_service: ModerationService, mock_bot: AsyncMock, mock_chat_repository: AsyncMock
    ):
        """Test global ban when no chats exist."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789

        mock_chat_repository.get_all.return_value = []

        # Act
        await moderation_service.ban_user_globally(admin_id=admin_id, user_id=user_id)

        # Assert - no calls should be made to ban_chat_member
        mock_bot.ban_chat_member.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_moderation_actions(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test concurrent moderation actions."""
        # Arrange
        admin_id = 987654321
        user_ids = [123456789, 234567890, 345678901]
        chat_id = -1001234567890
        duration = MuteDuration(minutes=5)

        mock_bot.restrict_chat_member.return_value = None

        # Act
        tasks = [
            moderation_service.mute_user(admin_id=admin_id, user_id=user_id, chat_id=chat_id, duration=duration)
            for user_id in user_ids
        ]

        await asyncio.gather(*tasks)

        # Assert
        assert mock_bot.restrict_chat_member.call_count == 3

    @pytest.mark.asyncio
    async def test_mute_duration_calculation(self, moderation_service: ModerationService, mock_bot: AsyncMock):
        """Test that mute duration is calculated correctly."""
        # Arrange
        admin_id = 987654321
        user_id = 123456789
        chat_id = -1001234567890
        duration = MuteDuration(minutes=10)

        mock_bot.restrict_chat_member.return_value = None

        # Act
        with patch("datetime.datetime") as mock_datetime:
            mock_now = datetime(2023, 1, 1, 12, 0, 0)
            mock_datetime.now.return_value = mock_now
            # Ensure that patched datetime.datetime can still be instantiated as normal,
            # while allowing us to control datetime.datetime.now().
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await moderation_service.mute_user(admin_id=admin_id, user_id=user_id, chat_id=chat_id, duration=duration)

        # Assert
        call_args = mock_bot.restrict_chat_member.call_args
        expected_until_date = mock_now + timedelta(seconds=600)  # 10 minutes
        assert call_args[1]["until_date"] == expected_until_date
