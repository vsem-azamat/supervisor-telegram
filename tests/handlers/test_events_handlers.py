"""Tests for event handlers - demonstrating user join/leave simulation."""

from unittest.mock import patch

import pytest
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

        # Mock logger to verify it was called
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act
            await user_joined(chat_member_update)

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

        # Mock logger to verify it was called
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act
            await user_left(chat_member_update)

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

        # Mock logger to verify it was called for each user
        with patch("app.presentation.telegram.handlers.events.logger") as mock_logger:
            # Act - Process all joins concurrently
            await asyncio.gather(*[user_joined(event) for event in join_events])

            # Assert - Logger should be called once for each user
            assert mock_logger.info.call_count == 3
            mock_logger.info.assert_called_with("User joined")
