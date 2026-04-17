"""Tests for domain exceptions — 3 essential assertions on the exception hierarchy."""

import pytest
from app.core.exceptions import DomainError, UserNotFoundException


@pytest.mark.unit
class TestDomainExceptions:
    def test_user_not_found_has_id_and_message(self):
        user_id = 123456789
        exception = UserNotFoundException(user_id)
        assert exception.user_id == user_id
        assert str(exception) == f"User with ID {user_id} not found"

    def test_user_not_found_is_domain_error(self):
        assert isinstance(UserNotFoundException(1), DomainError)

    def test_raise_and_catch(self):
        with pytest.raises(UserNotFoundException) as exc_info:
            raise UserNotFoundException(42)
        assert exc_info.value.user_id == 42
