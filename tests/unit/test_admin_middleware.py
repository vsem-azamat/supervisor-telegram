"""Tests for admin middlewares."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import types
from app.presentation.telegram.middlewares.admin import (
    AdminMiddleware,
    SuperAdminMiddleware,
    invalidate_admin_cache,
    you_are_not_admin,
)


def _make_message(user_id: int) -> MagicMock:
    msg = MagicMock(spec=types.Message)
    msg.from_user = MagicMock(spec=types.User)
    msg.from_user.id = user_id
    msg.answer = AsyncMock(return_value=MagicMock(spec=types.Message))
    msg.answer.return_value.delete = AsyncMock()
    msg.delete = AsyncMock()
    return msg


def _make_callback(user_id: int) -> MagicMock:
    cb = MagicMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(spec=types.User)
    cb.from_user.id = user_id
    return cb


class TestSuperAdminMiddleware:
    @pytest.fixture
    def middleware(self):
        return SuperAdminMiddleware()

    async def test_allows_super_admin(self, middleware):
        handler = AsyncMock()
        msg = _make_message(111)
        with patch("app.presentation.telegram.middlewares.admin.settings") as mock_settings:
            mock_settings.admin.super_admins = [111, 222]
            await middleware(handler, msg, {})
            handler.assert_called_once_with(msg, {})

    async def test_blocks_non_super_admin(self, middleware):
        handler = AsyncMock()
        msg = _make_message(999)
        with patch("app.presentation.telegram.middlewares.admin.settings") as mock_settings:
            mock_settings.admin.super_admins = [111]
            with patch("app.presentation.telegram.middlewares.admin.you_are_not_admin", new_callable=AsyncMock):
                result = await middleware(handler, msg, {})
                handler.assert_not_called()
                assert result is None

    async def test_allows_callback_query(self, middleware):
        handler = AsyncMock()
        cb = _make_callback(111)
        with patch("app.presentation.telegram.middlewares.admin.settings") as mock_settings:
            mock_settings.admin.super_admins = [111]
            await middleware(handler, cb, {})
            handler.assert_called_once()


class TestAdminMiddleware:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Invalidate admin cache before each test to ensure isolation."""
        invalidate_admin_cache()
        yield
        invalidate_admin_cache()

    @pytest.fixture
    def middleware(self):
        return AdminMiddleware()

    @pytest.fixture
    def admin_repo(self):
        return AsyncMock()

    async def test_allows_super_admin(self, middleware, admin_repo):
        handler = AsyncMock()
        msg = _make_message(111)
        admin_repo.get_db_admins = AsyncMock(return_value=[])
        with patch("app.presentation.telegram.middlewares.admin.settings") as mock_settings:
            mock_settings.admin.super_admins = [111]
            await middleware(handler, msg, {"admin_repo": admin_repo})
            handler.assert_called_once()

    async def test_allows_db_admin(self, middleware, admin_repo):
        handler = AsyncMock()
        msg = _make_message(333)
        db_admin = MagicMock()
        db_admin.id = 333
        admin_repo.get_db_admins = AsyncMock(return_value=[db_admin])
        with patch("app.presentation.telegram.middlewares.admin.settings") as mock_settings:
            mock_settings.admin.super_admins = [111]
            await middleware(handler, msg, {"admin_repo": admin_repo})
            handler.assert_called_once()

    async def test_blocks_regular_user(self, middleware, admin_repo):
        handler = AsyncMock()
        msg = _make_message(999)
        admin_repo.get_db_admins = AsyncMock(return_value=[])
        with patch("app.presentation.telegram.middlewares.admin.settings") as mock_settings:
            mock_settings.admin.super_admins = [111]
            with patch("app.presentation.telegram.middlewares.admin.you_are_not_admin", new_callable=AsyncMock):
                result = await middleware(handler, msg, {"admin_repo": admin_repo})
                handler.assert_not_called()
                assert result is None


class TestYouAreNotAdmin:
    async def test_sends_rejection_for_message(self):
        msg = _make_message(999)
        with patch("app.presentation.telegram.middlewares.admin.asyncio.sleep", new_callable=AsyncMock):
            await you_are_not_admin(msg)
            msg.answer.assert_called_once_with("🚫 You are not an Admin.")

    async def test_custom_text(self):
        msg = _make_message(999)
        with patch("app.presentation.telegram.middlewares.admin.asyncio.sleep", new_callable=AsyncMock):
            await you_are_not_admin(msg, "Custom denial")
            msg.answer.assert_called_once_with("Custom denial")

    async def test_noop_for_non_message(self):
        event = MagicMock(spec=types.CallbackQuery)
        # Should not raise
        await you_are_not_admin(event)
