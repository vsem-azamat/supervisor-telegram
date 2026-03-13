"""Tests for domain exceptions."""

import pytest
from app.core.exceptions import (
    DomainError,
    UserNotFoundException,
)


@pytest.mark.unit
class TestDomainExceptions:
    """Test domain exceptions."""

    def test_domain_error_base_exception(self):
        """Test DomainError base exception."""
        exception = DomainError("Base error message")

        assert str(exception) == "Base error message"
        assert isinstance(exception, Exception)

    def test_user_not_found_exception(self):
        """Test UserNotFoundException."""
        user_id = 123456789

        exception = UserNotFoundException(user_id)

        assert exception.user_id == user_id
        assert str(exception) == f"User with ID {user_id} not found"

    def test_user_not_found_inherits_domain_error(self):
        """Test that UserNotFoundException inherits from DomainError."""
        exception = UserNotFoundException(123)
        assert isinstance(exception, DomainError)
        assert isinstance(exception, Exception)

    def test_negative_user_ids(self):
        """Test exceptions with negative user IDs."""
        negative_user_id = -123456

        exception = UserNotFoundException(negative_user_id)
        assert exception.user_id == negative_user_id
        assert str(negative_user_id) in str(exception)

    def test_zero_id(self):
        """Test exceptions with zero IDs."""
        exception = UserNotFoundException(0)
        assert "0" in str(exception)

    def test_large_ids(self):
        """Test exceptions with large IDs."""
        large_id = 999999999999999

        exception = UserNotFoundException(large_id)
        assert exception.user_id == large_id
        assert str(large_id) in str(exception)

    def test_exception_can_be_raised_and_caught(self):
        """Test that exceptions can be raised and caught properly."""
        with pytest.raises(UserNotFoundException) as exc_info:
            raise UserNotFoundException(123)
        assert exc_info.value.user_id == 123


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
