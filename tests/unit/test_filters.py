"""Tests for telegram filters."""

from unittest.mock import AsyncMock, patch

import pytest
from aiogram import types
from app.presentation.telegram.utils.filters import AdminFilter, ChatTypeFilter, SuperAdminFilter


@pytest.mark.unit
class TestSuperAdminFilter:
    """Test SuperAdminFilter."""

    @pytest.fixture
    def filter_instance(self):
        return SuperAdminFilter()

    @pytest.fixture
    def mock_message(self):
        message = AsyncMock(spec=types.Message)
        message.from_user = AsyncMock()
        return message

    async def test_super_admin_allowed(self, filter_instance, mock_message):
        """Test that super admin is allowed."""
        with patch("app.presentation.telegram.utils.filters.settings") as mock_settings:
            mock_settings.admin.super_admins = [123456789, 987654321]
            mock_message.from_user.id = 123456789

            result = await filter_instance(mock_message)

            assert result is True

    async def test_non_super_admin_denied(self, filter_instance, mock_message):
        """Test that non-super admin is denied."""
        with patch("app.presentation.telegram.utils.filters.settings") as mock_settings:
            mock_settings.admin.super_admins = [123456789, 987654321]
            mock_message.from_user.id = 555555555

            result = await filter_instance(mock_message)

            assert result is False

    async def test_empty_super_admins_list(self, filter_instance, mock_message):
        """Test with empty super admins list."""
        with patch("app.presentation.telegram.utils.filters.settings") as mock_settings:
            mock_settings.admin.super_admins = []
            mock_message.from_user.id = 123456789

            result = await filter_instance(mock_message)

            assert result is False

    async def test_super_admin_no_from_user(self, filter_instance):
        """Test that message with no from_user returns False."""
        msg = AsyncMock(spec=types.Message)
        msg.from_user = None

        with patch("app.presentation.telegram.utils.filters.settings") as mock_settings:
            mock_settings.admin.super_admins = [123456789]

            result = await filter_instance(msg)

            assert result is False


@pytest.mark.unit
class TestAdminFilter:
    """Test AdminFilter."""

    @pytest.fixture
    def filter_instance(self):
        return AdminFilter()

    @pytest.fixture
    def mock_message(self):
        message = AsyncMock(spec=types.Message)
        message.from_user = AsyncMock()
        return message

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    async def test_admin_allowed(self, filter_instance, mock_message, mock_db_session):
        """Test that admin is allowed."""
        mock_message.from_user.id = 123456789

        with patch("app.presentation.telegram.utils.filters.get_admin_repository") as mock_get_repo:
            mock_repo = AsyncMock()

            mock_admin1 = AsyncMock()
            mock_admin1.id = 123456789
            mock_admin2 = AsyncMock()
            mock_admin2.id = 987654321

            mock_repo.get_db_admins.return_value = [mock_admin1, mock_admin2]
            mock_get_repo.return_value = mock_repo

            result = await filter_instance(mock_message, mock_db_session)

            assert result is True
            mock_get_repo.assert_called_once_with(mock_db_session)

    async def test_non_admin_denied(self, filter_instance, mock_message, mock_db_session):
        """Test that non-admin is denied."""
        mock_message.from_user.id = 555555555

        with patch("app.presentation.telegram.utils.filters.get_admin_repository") as mock_get_repo:
            mock_repo = AsyncMock()

            mock_admin1 = AsyncMock()
            mock_admin1.id = 123456789
            mock_admin2 = AsyncMock()
            mock_admin2.id = 987654321

            mock_repo.get_db_admins.return_value = [mock_admin1, mock_admin2]
            mock_get_repo.return_value = mock_repo

            result = await filter_instance(mock_message, mock_db_session)

            assert result is False

    async def test_empty_admins_list(self, filter_instance, mock_message, mock_db_session):
        """Test with empty admins list."""
        mock_message.from_user.id = 123456789

        with patch("app.presentation.telegram.utils.filters.get_admin_repository") as mock_get_repo:
            mock_repo = AsyncMock()
            mock_repo.get_db_admins.return_value = []
            mock_get_repo.return_value = mock_repo

            result = await filter_instance(mock_message, mock_db_session)

            assert result is False

    async def test_admin_no_from_user(self, filter_instance, mock_db_session):
        """Test that message with no from_user returns False."""
        msg = AsyncMock(spec=types.Message)
        msg.from_user = None

        with patch("app.presentation.telegram.utils.filters.get_admin_repository") as mock_get_repo:
            result = await filter_instance(msg, mock_db_session)

            assert result is False
            mock_get_repo.assert_not_called()


@pytest.mark.unit
class TestChatTypeFilter:
    """Test ChatTypeFilter."""

    @pytest.fixture
    def mock_message(self):
        message = AsyncMock(spec=types.Message)
        message.chat = AsyncMock()
        return message

    @pytest.mark.parametrize(
        ("chat_type_filter", "actual_type", "expected"),
        [
            ("group", "group", True),
            ("group", "private", False),
            (["group", "supergroup"], "supergroup", True),
            (["group", "supergroup"], "private", False),
        ],
        ids=["single_match", "single_no_match", "multi_match", "multi_no_match"],
    )
    async def test_chat_type_matching(self, mock_message, chat_type_filter, actual_type, expected):
        """Test chat type matching for single and list filters."""
        filter_instance = ChatTypeFilter(chat_type_filter)
        mock_message.chat.type = actual_type

        result = await filter_instance(mock_message)

        assert result is expected

    async def test_empty_chat_types_list(self, mock_message):
        """Test empty chat types list."""
        filter_instance = ChatTypeFilter([])
        mock_message.chat.type = "group"

        result = await filter_instance(mock_message)

        assert result is False

    async def test_case_sensitive_matching(self, mock_message):
        """Test that chat type matching is case sensitive."""
        filter_instance = ChatTypeFilter("GROUP")  # Uppercase
        mock_message.chat.type = "group"  # Lowercase

        result = await filter_instance(mock_message)

        assert result is False
