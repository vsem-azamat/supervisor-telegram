"""Tests for event handlers - demonstrating user join/leave simulation."""

from unittest.mock import AsyncMock, patch

import pytest
from app.domain.repositories import IChatRepository
from app.presentation.telegram.handlers.events import user_joined, user_left

from tests.telegram_helpers import (
    TelegramObjectFactory,
    create_normal_user,
    create_test_chat,
)


@pytest.mark.handlers
class TestEventHandlers:
    """Test cases for Telegram event handlers."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    async def test_user_joined_event(self, telegram_factory: TelegramObjectFactory):
        """Test handling user joining a chat."""
        from aiogram.types import ChatMemberLeft, ChatMemberMember

        # Arrange
        new_user = create_normal_user(id=123456789, username="newuser")
        chat = create_test_chat()

        # Create proper ChatMember objects
        old_member = ChatMemberLeft(user=new_user, status="left")
        new_member = ChatMemberMember(user=new_user, status="member")

        # Create user join event
        chat_member_update = telegram_factory.create_chat_member_updated(
            chat=chat,
            user=new_user,
            old_chat_member=old_member,
            new_chat_member=new_member,
        )

        # Mock logger and chat repository
        mock_chat_repo = AsyncMock(spec=IChatRepository)
        mock_chat_repo.get_by_id.return_value = None  # No chat found, should not trigger auto-delete log
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act
            await user_joined(chat_member_update, mock_chat_repo)

            # Assert
            mock_logger.info.assert_called_once_with("User joined")

    async def test_user_left_event(self, telegram_factory: TelegramObjectFactory):
        """Test handling user leaving a chat."""
        from aiogram.types import ChatMemberLeft, ChatMemberMember

        # Arrange
        leaving_user = create_normal_user(id=987654321, username="leaving_user")
        chat = create_test_chat()

        # Create proper ChatMember objects
        old_member = ChatMemberMember(user=leaving_user, status="member")
        new_member = ChatMemberLeft(user=leaving_user, status="left")

        # Create user leave event
        chat_member_update = telegram_factory.create_chat_member_updated(
            chat=chat,
            user=leaving_user,
            old_chat_member=old_member,
            new_chat_member=new_member,
        )

        # Mock logger and chat repository
        mock_chat_repo = AsyncMock(spec=IChatRepository)
        mock_chat_repo.get_by_id.return_value = None  # No chat found, should not trigger auto-delete log
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act
            await user_left(chat_member_update, mock_chat_repo)

            # Assert
            mock_logger.info.assert_called_once_with("User left")

    async def test_multiple_users_joining_simultaneously(self, telegram_factory: TelegramObjectFactory):
        """Test concurrent user joins."""
        import asyncio

        from aiogram.types import ChatMemberLeft, ChatMemberMember

        # Arrange
        chat = create_test_chat()
        new_users = [
            create_normal_user(id=100000001, username="user1"),
            create_normal_user(id=100000002, username="user2"),
            create_normal_user(id=100000003, username="user3"),
        ]

        # Create join events for all users
        join_events = []
        for user in new_users:
            old_member = ChatMemberLeft(user=user, status="left")
            new_member = ChatMemberMember(user=user, status="member")

            event = telegram_factory.create_chat_member_updated(
                chat=chat,
                user=user,
                old_chat_member=old_member,
                new_chat_member=new_member,
            )
            join_events.append(event)

        # Mock logger and chat repository
        mock_chat_repo = AsyncMock(spec=IChatRepository)
        mock_chat_repo.get_by_id.return_value = None  # No chat found, should not trigger auto-delete log
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act - Process all joins concurrently
            await asyncio.gather(*[user_joined(event, mock_chat_repo) for event in join_events])

            # Assert - Logger should be called once for each user
            assert mock_logger.info.call_count == 3
            mock_logger.info.assert_called_with("User joined")


@pytest.mark.handlers
class TestEventSimulatorUsage:
    """Test basic event creation without complex simulation."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    async def test_complete_user_workflow_simulation(self, telegram_factory: TelegramObjectFactory):
        """Test creating events for a complete user workflow."""
        from aiogram.types import ChatMemberLeft, ChatMemberMember

        # Arrange
        new_user = create_normal_user(id=555666777, username="troublemaker")
        chat = create_test_chat()

        # 1. Create user join event
        old_member = ChatMemberLeft(user=new_user, status="left")
        new_member = ChatMemberMember(user=new_user, status="member")

        join_event = telegram_factory.create_chat_member_updated(
            chat=chat,
            user=new_user,
            old_chat_member=old_member,
            new_chat_member=new_member,
        )

        assert join_event.new_chat_member.user.id == new_user.id

        # 2. Create a problematic message
        message = telegram_factory.create_message(user=new_user, chat=chat, text="🚨 SPAM MESSAGE 🚨")
        assert message.text == "🚨 SPAM MESSAGE 🚨"

        # Test completed successfully

    async def test_admin_interaction_simulation(self, telegram_factory: TelegramObjectFactory):
        """Test creating admin interaction events."""
        from tests.telegram_helpers import create_admin_user

        # Arrange
        admin = create_admin_user()
        target_user = create_normal_user(id=333444555, username="target")
        chat = create_test_chat()

        # 1. Create ban command message
        ban_message = telegram_factory.create_command_message(command="ban", user=admin, chat=chat)
        assert ban_message.text == "/ban"

        # 2. Create unban callback
        unban_callback = telegram_factory.create_callback_query(user=admin, data=f"unblock_{target_user.id}")

        # Test completed successfully - this verifies event creation works
        assert unban_callback.from_user.id == admin.id

    async def test_welcome_message_scenario(self, telegram_factory: TelegramObjectFactory):
        """Test welcome message flow for new users."""
        from aiogram.types import ChatMemberLeft, ChatMemberMember

        # Arrange
        new_user = create_normal_user(id=777888999, username="newcomer")
        chat = create_test_chat()

        # Create user join event
        old_member = ChatMemberLeft(user=new_user, status="left")
        new_member = ChatMemberMember(user=new_user, status="member")

        join_event = telegram_factory.create_chat_member_updated(
            chat=chat,
            user=new_user,
            old_chat_member=old_member,
            new_chat_member=new_member,
        )

        # Mock logger and chat repository
        mock_chat_repo = AsyncMock(spec=IChatRepository)
        mock_chat_repo.get_by_id.return_value = None  # No chat found, should not trigger auto-delete log
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act - Simulate what the actual event handler would do
            await user_joined(join_event, mock_chat_repo)

            # Assert
            mock_logger.info.assert_called_once_with("User joined")

        # Test completed successfully
        assert join_event.new_chat_member.user.username == "newcomer"
