"""Tests for domain exceptions."""

import pytest
from app.domain.exceptions import (
    AdminAlreadyExistsException,
    AdminNotFoundException,
    ChatNotFoundException,
    ConfigurationException,
    DomainError,
    InsufficientPermissionsException,
    InvalidModerationTargetException,
    TelegramApiException,
    UserAlreadyBlockedException,
    UserNotBlockedException,
    UserNotFoundException,
    ValidationException,
)


@pytest.mark.unit
class TestDomainExceptions:
    """Test domain exceptions."""

    def test_domain_error_base_exception(self):
        """Test DomainError base exception."""
        exception = DomainError("Base error message")

        assert str(exception) == "Base error message"
        assert isinstance(exception, Exception)

    def test_domain_error_inheritance(self):
        """Test that all domain exceptions inherit from DomainError."""
        exceptions = [
            UserNotFoundException(123),
            ChatNotFoundException(-456),
            AdminNotFoundException(789),
            UserAlreadyBlockedException(111),
            UserNotBlockedException(222),
            AdminAlreadyExistsException(333),
            InsufficientPermissionsException(444, "ban"),
            InvalidModerationTargetException("cannot moderate self"),
            TelegramApiException("sendMessage", "timeout"),
            ConfigurationException("missing key"),
            ValidationException("email", "bad@", "invalid format"),
        ]

        for exception in exceptions:
            assert isinstance(exception, DomainError)
            assert isinstance(exception, Exception)

    def test_user_not_found_exception(self):
        """Test UserNotFoundException."""
        user_id = 123456789

        exception = UserNotFoundException(user_id)

        assert exception.user_id == user_id
        assert str(exception) == f"User with ID {user_id} not found"

    def test_chat_not_found_exception(self):
        """Test ChatNotFoundException."""
        chat_id = -1001234567890

        exception = ChatNotFoundException(chat_id)

        assert exception.chat_id == chat_id
        assert str(exception) == f"Chat with ID {chat_id} not found"

    def test_admin_not_found_exception(self):
        """Test AdminNotFoundException."""
        admin_id = 987654321

        exception = AdminNotFoundException(admin_id)

        assert exception.admin_id == admin_id
        assert str(exception) == f"Admin with ID {admin_id} not found"

    def test_user_already_blocked_exception(self):
        """Test UserAlreadyBlockedException."""
        user_id = 555555555

        exception = UserAlreadyBlockedException(user_id)

        assert exception.user_id == user_id
        assert str(exception) == f"User {user_id} is already blocked"

    def test_user_not_blocked_exception(self):
        """Test UserNotBlockedException."""
        user_id = 777777777

        exception = UserNotBlockedException(user_id)

        assert exception.user_id == user_id
        assert str(exception) == f"User {user_id} is not blocked"

    def test_admin_already_exists_exception(self):
        """Test AdminAlreadyExistsException."""
        admin_id = 123

        exception = AdminAlreadyExistsException(admin_id)

        assert exception.admin_id == admin_id
        assert str(exception) == "Admin 123 already exists"

    def test_insufficient_permissions_exception(self):
        """Test InsufficientPermissionsException."""
        exception = InsufficientPermissionsException(42, "ban")

        assert exception.user_id == 42
        assert exception.action == "ban"
        assert "42" in str(exception)
        assert "ban" in str(exception)

    def test_invalid_moderation_target_exception(self):
        """Test InvalidModerationTargetException."""
        exception = InvalidModerationTargetException("cannot moderate bot")

        assert str(exception) == "cannot moderate bot"

    def test_telegram_api_exception(self):
        """Test TelegramApiException stores operation and error."""
        exception = TelegramApiException("sendMessage", "Bad Request: chat not found")

        assert exception.operation == "sendMessage"
        assert exception.error == "Bad Request: chat not found"
        assert "sendMessage" in str(exception)
        assert "Bad Request: chat not found" in str(exception)

    def test_configuration_exception(self):
        """Test ConfigurationException."""
        exception = ConfigurationException("missing BOT_TOKEN")

        assert "missing BOT_TOKEN" in str(exception)

    def test_validation_exception(self):
        """Test ValidationException stores field and value."""
        exception = ValidationException("email", "bad@", "invalid format")

        assert exception.field == "email"
        assert exception.value == "bad@"
        assert "email" in str(exception)
        assert "bad@" in str(exception)

    def test_exceptions_can_be_raised_and_caught(self):
        """Test that exceptions can be raised and caught properly."""
        with pytest.raises(UserNotFoundException) as exc_info:
            raise UserNotFoundException(123)
        assert exc_info.value.user_id == 123

        with pytest.raises(ChatNotFoundException) as exc_info:
            raise ChatNotFoundException(-456)
        assert exc_info.value.chat_id == -456

        with pytest.raises(AdminNotFoundException) as exc_info:
            raise AdminNotFoundException(789)
        assert exc_info.value.admin_id == 789

        with pytest.raises(UserAlreadyBlockedException) as exc_info:
            raise UserAlreadyBlockedException(111)
        assert exc_info.value.user_id == 111

        with pytest.raises(UserNotBlockedException) as exc_info:
            raise UserNotBlockedException(222)
        assert exc_info.value.user_id == 222

    def test_negative_user_ids(self):
        """Test exceptions with negative user IDs."""
        negative_user_id = -123456

        exception = UserNotFoundException(negative_user_id)
        assert exception.user_id == negative_user_id
        assert str(negative_user_id) in str(exception)

    @pytest.mark.parametrize(
        ("exc_cls", "kwargs"),
        [
            (UserNotFoundException, {"user_id": 0}),
            (ChatNotFoundException, {"chat_id": 0}),
            (AdminNotFoundException, {"admin_id": 0}),
            (UserAlreadyBlockedException, {"user_id": 0}),
            (UserNotBlockedException, {"user_id": 0}),
        ],
    )
    def test_zero_ids(self, exc_cls, kwargs):
        """Test exceptions with zero IDs."""
        exception = exc_cls(*kwargs.values())
        assert "0" in str(exception)

    def test_large_ids(self):
        """Test exceptions with large IDs."""
        large_id = 999999999999999

        exception = UserNotFoundException(large_id)
        assert exception.user_id == large_id
        assert str(large_id) in str(exception)


@pytest.mark.unit
class TestExceptionChaining:
    """Test exception chaining and context."""

    def test_exception_can_be_chained(self):
        """Test that domain exceptions can be chained with other exceptions."""
        original_error = ValueError("Original error")
        with pytest.raises(UserNotFoundException) as exc_info:
            raise UserNotFoundException(123) from original_error
        assert exc_info.value.user_id == 123
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert str(exc_info.value.__cause__) == "Original error"
