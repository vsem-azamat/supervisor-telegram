"""Unit tests for domain entities."""

import pytest
from app.domain.entities import UserEntity

from tests.factories import ChatFactory, ChatLinkFactory, MessageFactory, UserFactory


class TestUserEntity:
    """Test cases for UserEntity."""

    def test_user_display_name_full_name(self):
        """Test display name with first and last name."""
        user = UserFactory.create(first_name="John", last_name="Doe", username="johndoe")

        assert user.display_name == "John Doe"

    def test_user_display_name_first_name_only(self):
        """Test display name with only first name."""
        user = UserEntity(id=123456, first_name="John", last_name=None, username="johndoe")

        assert user.display_name == "John"

    def test_user_display_name_username_only(self):
        """Test display name with only username."""
        user = UserEntity(id=123456, first_name=None, last_name=None, username="johndoe")

        assert user.display_name == "@johndoe"

    def test_user_display_name_fallback(self):
        """Test display name fallback to user ID."""
        user = UserEntity(id=123456, first_name=None, last_name=None, username=None)

        assert user.display_name == "User 123456"

    def test_block_user(self):
        """Test blocking a user."""
        user = UserFactory.create(is_blocked=False)

        user.block()

        assert user.is_blocked is True

    def test_unblock_user(self):
        """Test unblocking a user."""
        user = UserFactory.create_blocked()

        user.unblock()

        assert user.is_blocked is False

    def test_user_equality(self):
        """Test user entity equality via dataclass __eq__."""
        user1 = UserEntity(id=123456, username="a", first_name="A", last_name="B")
        user2 = UserEntity(id=123456, username="a", first_name="A", last_name="B")
        user3 = UserEntity(id=654321, username="a", first_name="A", last_name="B")

        assert user1 == user2
        assert user1 != user3


class TestChatEntity:
    """Test cases for ChatEntity."""

    def test_enable_welcome_message(self):
        """Test enabling welcome message."""
        chat = ChatFactory.create(is_welcome_enabled=False)

        chat.enable_welcome("Hello everyone!")

        assert chat.is_welcome_enabled is True
        assert chat.welcome_message == "Hello everyone!"

    def test_enable_welcome_without_message(self):
        """Test enabling welcome without changing message."""
        chat = ChatFactory.create(welcome_message="Original message", is_welcome_enabled=False)

        chat.enable_welcome()

        assert chat.is_welcome_enabled is True
        assert chat.welcome_message == "Original message"

    def test_disable_welcome_message(self):
        """Test disabling welcome message."""
        chat = ChatFactory.create_with_welcome()

        chat.disable_welcome()

        assert chat.is_welcome_enabled is False

    def test_set_welcome_delete_time_valid(self):
        """Test setting valid welcome delete time."""
        chat = ChatFactory.create()

        chat.set_welcome_delete_time(120)

        assert chat.welcome_delete_time == 120

    @pytest.mark.parametrize("invalid_seconds", [0, -10, -1])
    def test_set_welcome_delete_time_invalid(self, invalid_seconds):
        """Test setting invalid welcome delete time."""
        chat = ChatFactory.create()

        with pytest.raises(ValueError, match="Delete time must be positive"):
            chat.set_welcome_delete_time(invalid_seconds)

    def test_enable_captcha(self):
        """Test enabling captcha."""
        chat = ChatFactory.create(is_captcha_enabled=False)

        chat.enable_captcha()

        assert chat.is_captcha_enabled is True

    def test_disable_captcha(self):
        """Test disabling captcha."""
        chat = ChatFactory.create(is_captcha_enabled=True)

        chat.disable_captcha()

        assert chat.is_captcha_enabled is False


class TestAdminEntity:
    """Test cases for AdminEntity."""

    def test_activate_admin(self):
        """Test activating an admin."""
        from tests.factories import AdminFactory

        admin = AdminFactory.create_inactive()

        admin.activate()

        assert admin.is_active is True

    def test_deactivate_admin(self):
        """Test deactivating an admin."""
        from tests.factories import AdminFactory

        admin = AdminFactory.create(is_active=True)

        admin.deactivate()

        assert admin.is_active is False


class TestMessageEntity:
    """Test cases for MessageEntity."""

    def test_mark_message_as_spam(self):
        """Test marking message as spam."""
        message = MessageFactory.create(is_spam=False)

        message.mark_as_spam()

        assert message.is_spam is True

    def test_unmark_message_as_spam(self):
        """Test unmarking message as spam."""
        message = MessageFactory.create_spam()

        message.unmark_as_spam()

        assert message.is_spam is False

    def test_message_with_empty_metadata(self):
        """Test message with empty metadata."""
        message = MessageFactory.create(metadata=None)

        # Should handle None metadata gracefully
        assert message.metadata is None or message.metadata == {}


class TestChatLinkEntity:
    """Test cases for ChatLinkEntity."""

    @pytest.mark.parametrize(
        ("initial", "new_priority"),
        [
            (0, 10),
            (5, 0),
            (0, -1),
            (5, -1),
            (10, 100),
        ],
    )
    def test_update_priority(self, initial, new_priority):
        """Test updating link priority (including negative values)."""
        link = ChatLinkFactory.create(priority=initial)

        link.update_priority(new_priority)

        assert link.priority == new_priority
