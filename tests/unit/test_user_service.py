"""Unit tests for UserService."""

from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import UserNotFoundException
from app.db.models import User
from app.db.repositories.user import UserRepository
from app.moderation.user_service import UserService

from tests.factories import UserFactory

LOGGER_PATCH_PATH = "app.moderation.user_service.logger"


# --- Module-level fixtures (shared by all test classes) ---


@pytest.fixture
def mock_user_repository() -> AsyncMock:
    """Create a mock user repository."""
    return AsyncMock(spec=UserRepository)


@pytest.fixture
def user_service(mock_user_repository: AsyncMock) -> UserService:
    """Create UserService with mocked dependencies."""
    return UserService(mock_user_repository)


class TestUserService:
    """Test cases for UserService."""

    async def test_get_user_by_id_not_found(self, user_service: UserService, mock_user_repository: AsyncMock):
        """Test getting user by ID when user doesn't exist."""
        user_id = 999999999
        mock_user_repository.get_by_id.return_value = None

        with pytest.raises(UserNotFoundException) as exc_info:
            await user_service.get_user_by_id(user_id)

        assert exc_info.value.user_id == user_id

    async def test_get_user_by_id_optional_not_found(self, user_service: UserService, mock_user_repository: AsyncMock):
        """Test getting user by ID (optional) when user doesn't exist."""
        user_id = 999999999
        mock_user_repository.get_by_id.return_value = None

        result = await user_service.get_user_by_id_optional(user_id)

        assert result is None

    async def test_create_or_update_user_existing_user(self, mock_user_repository: AsyncMock):
        """Test updating an existing user (verifies branch, not log string)."""
        user_id = 123456789
        existing_user = UserFactory.create(id=user_id, username="oldusername", first_name="Old", last_name="Name")

        updated_user = UserFactory.create(id=user_id, username="newusername", first_name="New", last_name="Name")

        mock_user_repository.get_by_id.return_value = existing_user
        mock_user_repository.save.return_value = updated_user

        with patch(LOGGER_PATCH_PATH):
            service = UserService(mock_user_repository)
            result = await service.create_or_update_user(
                user_id=user_id, username="newusername", first_name="New", last_name="Name"
            )

        assert result.username == "newusername"
        assert result.first_name == "New"
        mock_user_repository.save.assert_called_once()

    async def test_block_user_existing_user(self, mock_user_repository: AsyncMock):
        """Test blocking an existing user."""
        user_id = 123456789
        existing_user = UserFactory.create(id=user_id, is_blocked=False)
        blocked_user = UserFactory.create(id=user_id, is_blocked=True)

        mock_user_repository.get_by_id.return_value = existing_user
        mock_user_repository.save.return_value = blocked_user

        with patch(LOGGER_PATCH_PATH) as mock_logger:
            service = UserService(mock_user_repository)
            result = await service.block_user(user_id)

        assert result.is_blocked is True

        mock_user_repository.get_by_id.assert_called_once_with(user_id)
        mock_user_repository.save.assert_called_once()
        mock_logger.info.assert_called_once_with("user_blocked", user_id=user_id)

    async def test_block_user_nonexistent_user(self, mock_user_repository: AsyncMock):
        """Test blocking a non-existent user (creates new blocked user)."""
        user_id = 123456789
        new_blocked_user = UserFactory.create(id=user_id, is_blocked=True)

        mock_user_repository.get_by_id.return_value = None
        mock_user_repository.save.return_value = new_blocked_user

        with patch(LOGGER_PATCH_PATH) as mock_logger:
            service = UserService(mock_user_repository)
            result = await service.block_user(user_id)

        assert result.is_blocked is True
        assert result.id == user_id

        mock_user_repository.get_by_id.assert_called_once_with(user_id)
        mock_user_repository.save.assert_called_once()
        mock_logger.info.assert_called_once_with("user_blocked", user_id=user_id)

    async def test_unblock_user_success(self, mock_user_repository: AsyncMock):
        """Test successfully unblocking a user."""
        user_id = 123456789
        blocked_user = UserFactory.create(id=user_id, is_blocked=True)
        unblocked_user = UserFactory.create(id=user_id, is_blocked=False)

        mock_user_repository.get_by_id.return_value = blocked_user
        mock_user_repository.save.return_value = unblocked_user

        with patch(LOGGER_PATCH_PATH) as mock_logger:
            service = UserService(mock_user_repository)
            result = await service.unblock_user(user_id)

        assert result.is_blocked is False

        mock_user_repository.get_by_id.assert_called_once_with(user_id)
        mock_user_repository.save.assert_called_once()
        mock_logger.info.assert_called_once_with("user_unblocked", user_id=user_id)

    async def test_unblock_user_not_blocked(self, mock_user_repository: AsyncMock):
        """Test unblocking a user that isn't blocked."""
        user_id = 123456789
        user = UserFactory.create(id=user_id, is_blocked=False)

        mock_user_repository.get_by_id.return_value = user

        with patch(LOGGER_PATCH_PATH) as mock_logger:
            service = UserService(mock_user_repository)
            result = await service.unblock_user(user_id)

        assert result.is_blocked is False

        mock_user_repository.get_by_id.assert_called_once_with(user_id)
        # save should not be called since user wasn't blocked
        mock_user_repository.save.assert_not_called()
        mock_logger.info.assert_called_once_with("unblock_attempt_not_blocked", user_id=user_id)

    async def test_unblock_user_not_found(self, user_service: UserService, mock_user_repository: AsyncMock):
        """Test unblocking a user that doesn't exist."""
        user_id = 999999999
        mock_user_repository.get_by_id.return_value = None

        with pytest.raises(UserNotFoundException) as exc_info:
            await user_service.unblock_user(user_id)

        assert exc_info.value.user_id == user_id
        mock_user_repository.get_by_id.assert_called_once_with(user_id)
        mock_user_repository.save.assert_not_called()


@pytest.mark.unit
class TestUserServiceEdgeCases:
    """Test edge cases and error conditions for UserService."""

    async def test_create_or_update_user_partial_data(self, user_service: UserService, mock_user_repository: AsyncMock):
        """Test creating user with partial data (some None values)."""
        user_id = 123456789
        mock_user_repository.get_by_id.return_value = None
        expected_user = User(id=user_id, username=None, first_name="Test", last_name=None, verify=False, blocked=False)
        mock_user_repository.save.return_value = expected_user

        with patch(LOGGER_PATCH_PATH):
            result = await user_service.create_or_update_user(
                user_id=user_id, username=None, first_name="Test", last_name=None
            )

        assert result.id == user_id
        assert result.username is None
        assert result.first_name == "Test"
        assert result.last_name is None
