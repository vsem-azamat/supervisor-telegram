"""Unit tests for domain value objects."""

import pytest
from app.domain.value_objects import (
    MAX_MUTE_DURATION_MINUTES,
    ChatId,
    ChatType,
    EscalationStatus,
    MessageId,
    ModerationAction,
    MuteDuration,
    PostStatus,
    UserId,
    UserProfile,
    WelcomeSettings,
)


class TestPostStatus:
    """Test cases for PostStatus StrEnum."""

    def test_values(self):
        assert PostStatus.DRAFT == "draft"
        assert PostStatus.SCHEDULED == "scheduled"
        assert PostStatus.APPROVED == "approved"
        assert PostStatus.REJECTED == "rejected"

    def test_is_str(self):
        assert isinstance(PostStatus.DRAFT, str)

    def test_all_members(self):
        assert set(PostStatus) == {
            PostStatus.DRAFT,
            PostStatus.SCHEDULED,
            PostStatus.APPROVED,
            PostStatus.REJECTED,
        }


class TestEscalationStatus:
    """Test cases for EscalationStatus StrEnum."""

    def test_values(self):
        assert EscalationStatus.PENDING == "pending"
        assert EscalationStatus.RESOLVED == "resolved"
        assert EscalationStatus.TIMEOUT == "timeout"

    def test_is_str(self):
        assert isinstance(EscalationStatus.PENDING, str)

    def test_all_members(self):
        assert set(EscalationStatus) == {
            EscalationStatus.PENDING,
            EscalationStatus.RESOLVED,
            EscalationStatus.TIMEOUT,
        }


class TestModerationAction:
    """Test cases for ModerationAction enum."""

    def test_moderation_action_values(self):
        """Test all moderation action values."""
        assert ModerationAction.MUTE.value == "mute"
        assert ModerationAction.UNMUTE.value == "unmute"
        assert ModerationAction.BAN.value == "ban"
        assert ModerationAction.UNBAN.value == "unban"
        assert ModerationAction.KICK.value == "kick"
        assert ModerationAction.WARN.value == "warn"
        assert ModerationAction.DELETE_MESSAGE.value == "delete_message"

    def test_moderation_action_enum_membership(self):
        """Test enum membership."""
        assert ModerationAction.MUTE in ModerationAction
        assert "invalid_action" not in [action.value for action in ModerationAction]


class TestChatType:
    """Test cases for ChatType enum."""

    def test_chat_type_values(self):
        """Test all chat type values."""
        assert ChatType.PRIVATE.value == "private"
        assert ChatType.GROUP.value == "group"
        assert ChatType.SUPERGROUP.value == "supergroup"
        assert ChatType.CHANNEL.value == "channel"


class TestUserId:
    """Test cases for UserId value object."""

    def test_create_valid_user_id(self):
        """Test creating valid user ID."""
        user_id = UserId(123456789)

        assert user_id.value == 123456789

    def test_user_id_immutable(self):
        """Test that UserId is immutable."""
        user_id = UserId(123456789)

        with pytest.raises(AttributeError):
            user_id.value = 987654321

    def test_user_id_equality(self):
        """Test UserId equality."""
        user_id1 = UserId(123456789)
        user_id2 = UserId(123456789)
        user_id3 = UserId(987654321)

        assert user_id1 == user_id2
        assert user_id1 != user_id3

    def test_user_id_validation_zero(self):
        """Test UserId validation with zero."""
        with pytest.raises(ValueError, match="User ID must be positive"):
            UserId(0)

    def test_user_id_validation_negative(self):
        """Test UserId validation with negative value."""
        with pytest.raises(ValueError, match="User ID must be positive"):
            UserId(-123)


class TestChatId:
    """Test cases for ChatId value object."""

    def test_create_valid_positive_chat_id(self):
        """Test creating valid positive chat ID."""
        chat_id = ChatId(123456789)

        assert chat_id.value == 123456789

    def test_create_valid_negative_chat_id(self):
        """Test creating valid negative chat ID (supergroup/channel)."""
        chat_id = ChatId(-1001234567890)

        assert chat_id.value == -1001234567890

    def test_chat_id_validation_zero(self):
        """Test ChatId validation with zero."""
        with pytest.raises(ValueError, match="Chat ID cannot be zero"):
            ChatId(0)

    def test_chat_id_immutable(self):
        """Test that ChatId is immutable."""
        chat_id = ChatId(-1001234567890)

        with pytest.raises(AttributeError):
            chat_id.value = -9876543210


class TestMessageId:
    """Test cases for MessageId value object."""

    def test_create_valid_message_id(self):
        """Test creating valid message ID."""
        message_id = MessageId(42)

        assert message_id.value == 42

    def test_message_id_validation_zero(self):
        """Test MessageId validation with zero."""
        with pytest.raises(ValueError, match="Message ID must be positive"):
            MessageId(0)

    def test_message_id_validation_negative(self):
        """Test MessageId validation with negative value."""
        with pytest.raises(ValueError, match="Message ID must be positive"):
            MessageId(-1)


class TestMuteDuration:
    """Test cases for MuteDuration value object."""

    @pytest.mark.parametrize(
        ("minutes", "expected_seconds"),
        [
            (5, 300),
            (10, 600),
            (60, 3600),
            (1, 60),
        ],
    )
    def test_create_valid_mute_duration(self, minutes, expected_seconds):
        """Test creating valid mute duration and seconds calculation."""
        duration = MuteDuration(minutes=minutes)

        assert duration.minutes == minutes
        assert duration.seconds == expected_seconds

    def test_mute_duration_validation_zero(self):
        """Test MuteDuration validation with zero."""
        with pytest.raises(ValueError, match="Mute duration must be positive"):
            MuteDuration(minutes=0)

    def test_mute_duration_validation_negative(self):
        """Test MuteDuration validation with negative value."""
        with pytest.raises(ValueError, match="Mute duration must be positive"):
            MuteDuration(minutes=-5)

    def test_mute_duration_validation_too_long(self):
        """Test MuteDuration validation with excessive duration."""
        with pytest.raises(ValueError, match="Mute duration cannot exceed 1 year"):
            MuteDuration(minutes=MAX_MUTE_DURATION_MINUTES + 1)  # More than 1 year

    def test_mute_duration_max_allowed(self):
        """Test maximum allowed mute duration."""
        duration = MuteDuration(minutes=MAX_MUTE_DURATION_MINUTES)  # Exactly 1 year

        assert duration.minutes == MAX_MUTE_DURATION_MINUTES
        assert duration.seconds == 365 * 24 * 60 * 60  # 1 year in seconds (365 days)


class TestWelcomeSettings:
    """Test cases for WelcomeSettings value object."""

    def test_create_disabled_welcome_settings(self):
        """Test creating disabled welcome settings."""
        settings = WelcomeSettings(enabled=False)

        assert settings.enabled is False
        assert settings.message is None
        assert settings.delete_after_seconds == 60
        assert settings.captcha_enabled is False

    def test_create_enabled_welcome_settings(self):
        """Test creating enabled welcome settings."""
        settings = WelcomeSettings(
            enabled=True, message="Welcome to our chat!", delete_after_seconds=120, captcha_enabled=True
        )

        assert settings.enabled is True
        assert settings.message == "Welcome to our chat!"
        assert settings.delete_after_seconds == 120
        assert settings.captcha_enabled is True

    def test_welcome_settings_validation_enabled_without_message(self):
        """Test validation when enabled without message."""
        with pytest.raises(ValueError, match="Welcome message text is required when enabled"):
            WelcomeSettings(enabled=True, message=None)

    def test_welcome_settings_validation_invalid_delete_time_zero(self):
        """Test validation with zero delete time."""
        with pytest.raises(ValueError, match="Delete time must be positive"):
            WelcomeSettings(enabled=True, message="Welcome!", delete_after_seconds=0)

    def test_welcome_settings_validation_invalid_delete_time_negative(self):
        """Test validation with negative delete time."""
        with pytest.raises(ValueError, match="Delete time must be positive"):
            WelcomeSettings(enabled=True, message="Welcome!", delete_after_seconds=-10)

    def test_welcome_settings_immutable(self):
        """Test that WelcomeSettings is immutable."""
        settings = WelcomeSettings(enabled=True, message="Welcome!", delete_after_seconds=60)

        with pytest.raises(AttributeError):
            settings.enabled = False


class TestUserProfile:
    """Test cases for UserProfile value object."""

    def test_create_complete_user_profile(self):
        """Test creating complete user profile."""
        profile = UserProfile(username="johndoe", first_name="John", last_name="Doe")

        assert profile.username == "johndoe"
        assert profile.first_name == "John"
        assert profile.last_name == "Doe"

    def test_user_profile_display_name_full(self):
        """Test display name with full name."""
        profile = UserProfile(username="johndoe", first_name="John", last_name="Doe")

        assert profile.display_name == "John Doe"

    def test_user_profile_display_name_first_only(self):
        """Test display name with first name only."""
        profile = UserProfile(username="johndoe", first_name="John", last_name=None)

        assert profile.display_name == "John"

    def test_user_profile_display_name_username_only(self):
        """Test display name with username only."""
        profile = UserProfile(username="johndoe", first_name=None, last_name=None)

        assert profile.display_name == "@johndoe"

    def test_user_profile_display_name_fallback(self):
        """Test display name fallback."""
        profile = UserProfile(username=None, first_name=None, last_name=None)

        assert profile.display_name == "Unknown User"

    def test_user_profile_mention(self):
        """Test user mention property."""
        profile = UserProfile(username="johndoe", first_name="John", last_name="Doe")

        assert profile.mention == "@johndoe"

    def test_user_profile_mention_without_username(self):
        """Test user mention without username."""
        profile = UserProfile(username=None, first_name="John", last_name="Doe")

        assert profile.mention == "John Doe"

    def test_user_profile_immutable(self):
        """Test that UserProfile is immutable."""
        profile = UserProfile(username="johndoe", first_name="John")

        with pytest.raises(AttributeError):
            profile.username = "janedoe"
