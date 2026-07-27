"""Tests for BlacklistMiddleware."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberBanned, ChatMemberMember, TelegramObject
from app.presentation.telegram.middlewares import black_list
from app.presentation.telegram.middlewares.black_list import BlacklistMiddleware

from tests.telegram_helpers import MockBot, TelegramObjectFactory, create_normal_user, create_test_chat


class MockHandler:
    """Mock handler for middleware testing."""

    def __init__(self):
        self.called = False
        self.call_args = None

    async def __call__(self, event: TelegramObject, data: dict[str, Any]) -> None:
        self.called = True
        self.call_args = (event, data)


@pytest.mark.middleware
class TestBlacklistMiddleware:
    """Test cases for BlacklistMiddleware."""

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def mock_user_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_bot(self):
        return MockBot()

    @pytest.fixture(autouse=True)
    def _clear_blacklist_cache(self):
        """Reset the blacklist cache before each test."""
        black_list._blacklist_cache = None

    @pytest.fixture
    def blacklist_middleware(self):
        return BlacklistMiddleware()

    @pytest.fixture
    def mock_handler(self):
        return MockHandler()

    async def test_blacklist_middleware_allows_non_blocked_user(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware allows non-blocked users to proceed."""
        normal_user = create_normal_user()
        chat = create_test_chat()

        message = telegram_factory.create_message(user=normal_user, chat=chat, text="Hello world!")

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock no blocked users
        mock_user_repo.get_blocked_users.return_value = []

        await blacklist_middleware(mock_handler, message, data)

        assert mock_handler.called is True
        mock_user_repo.get_blocked_users.assert_called_once()

    async def test_blacklist_middleware_blocks_blacklisted_user(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware blocks blacklisted users."""
        blocked_user = create_normal_user(id=999, username="blocked_user")
        chat = create_test_chat()

        message = telegram_factory.create_message(
            user=blocked_user, chat=chat, text="I'm blocked but trying to send message"
        )

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock user is blocked
        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = blocked_user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        # Mock bot methods
        mock_bot.mock.ban_chat_member = AsyncMock()

        # Mock message delete method using patch
        with patch.object(message, "delete", new=AsyncMock()) as mock_delete:
            result = await blacklist_middleware(mock_handler, message, data)

            assert result is None  # Should stop processing
            assert mock_handler.called is False  # Handler should not be called
            mock_bot.mock.ban_chat_member.assert_called_once_with(chat.id, blocked_user.id)
            mock_delete.assert_called_once()

    async def test_blacklist_middleware_propagates_repository_errors(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware propagates repository errors (does not swallow them)."""
        user = create_normal_user()
        chat = create_test_chat()

        message = telegram_factory.create_message(user=user, chat=chat)

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock repository error
        mock_user_repo.get_blocked_users.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await blacklist_middleware(mock_handler, message, data)

    async def test_blacklist_middleware_missing_dependencies(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
    ):
        """Test middleware when dependencies are missing."""
        user = create_normal_user()
        chat = create_test_chat()

        message = telegram_factory.create_message(user=user, chat=chat)

        data: dict[str, Any] = {}  # No dependencies

        with pytest.raises(KeyError):
            await blacklist_middleware(mock_handler, message, data)

    async def test_blacklist_middleware_with_bot_messages(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_handler: MockHandler,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware with bot messages."""
        bot_user = create_normal_user(id=12345, is_bot=True)
        chat = create_test_chat()

        message = telegram_factory.create_message(user=bot_user, chat=chat, text="Bot message")

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # Mock bot is in blocked list
        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = bot_user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        # Mock bot methods
        mock_bot.mock.ban_chat_member = AsyncMock()

        # Mock message delete method using patch
        with patch.object(message, "delete", new=AsyncMock()) as mock_delete:
            result = await blacklist_middleware(mock_handler, message, data)

            # Should block bots too
            assert result is None
            mock_bot.mock.ban_chat_member.assert_called_once_with(chat.id, bot_user.id)
            mock_delete.assert_called_once()

    async def test_blacklist_middleware_performance_with_multiple_calls(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware performance with multiple concurrent calls."""
        import asyncio

        users = [create_normal_user(id=i) for i in range(100, 110)]
        chat = create_test_chat()

        messages = [telegram_factory.create_message(user=user, chat=chat) for user in users]

        mock_handlers = [MockHandler() for _ in messages]

        # Mock no blocked users
        mock_user_repo.get_blocked_users.return_value = []

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        tasks = [
            blacklist_middleware(handler, message, data)
            for handler, message in zip(mock_handlers, messages, strict=True)
        ]
        await asyncio.gather(*tasks)

        for handler in mock_handlers:
            assert handler.called is True

        # With TTL cache, get_blocked_users is called only once (cache serves subsequent calls)
        assert mock_user_repo.get_blocked_users.call_count == 1


@pytest.mark.middleware
class TestBlacklistMiddlewareEdgeCases:
    """Test edge cases for BlacklistMiddleware."""

    @pytest.fixture(autouse=True)
    def _clear_blacklist_cache(self):
        """Reset the blacklist cache before each test."""
        black_list._blacklist_cache = None

    @pytest.fixture
    def telegram_factory(self):
        return TelegramObjectFactory()

    @pytest.fixture
    def mock_user_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_bot(self):
        return MockBot()

    @pytest.fixture
    def blacklist_middleware(self):
        return BlacklistMiddleware()

    async def test_blacklist_middleware_with_callback_query(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware bypasses callback queries via type check (even for blocked users)."""
        blocked_user = create_normal_user(id=999)

        callback_query = telegram_factory.create_callback_query(user=blocked_user)

        mock_handler = MockHandler()
        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        # User IS blocked, but callback queries bypass the Message type check
        mock_blocked = AsyncMock()
        mock_blocked.id = blocked_user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked]

        await blacklist_middleware(mock_handler, callback_query, data)

        # Should allow callback queries through (they're not Message events)
        assert mock_handler.called is True

    async def test_blacklisted_user_banned_on_rejoin(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """A blacklisted user who rejoins is banned at the door.

        Waiting for their first message gives them the floor once, which is
        exactly what the blacklist exists to prevent.
        """
        user = create_normal_user()
        chat = create_test_chat()
        join = telegram_factory.create_chat_member_updated(chat=chat, user=user)

        mock_handler = MockHandler()
        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        await blacklist_middleware(mock_handler, join, data)

        mock_bot.mock.ban_chat_member.assert_awaited_once_with(chat.id, user.id)
        assert mock_handler.called is False

    async def test_normal_user_may_join(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """An ordinary join is untouched."""
        user = create_normal_user()
        join = telegram_factory.create_chat_member_updated(chat=create_test_chat(), user=user)

        mock_handler = MockHandler()
        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}
        mock_user_repo.get_blocked_users.return_value = []

        await blacklist_middleware(mock_handler, join, data)

        mock_bot.mock.ban_chat_member.assert_not_awaited()
        assert mock_handler.called is True

    async def test_our_own_ban_does_not_retrigger(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Banning emits its own chat_member update; it must not feed back."""
        user = create_normal_user()
        chat = create_test_chat()
        kicked = telegram_factory.create_chat_member_updated(
            chat=chat,
            user=user,
            old_chat_member=ChatMemberMember(user=user, status=ChatMemberStatus.MEMBER),
            new_chat_member=ChatMemberBanned(
                user=user, status=ChatMemberStatus.KICKED, until_date=datetime(1970, 1, 1, tzinfo=UTC)
            ),
        )

        mock_handler = MockHandler()
        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        mock_blocked_user = AsyncMock()
        mock_blocked_user.id = user.id
        mock_user_repo.get_blocked_users.return_value = [mock_blocked_user]

        await blacklist_middleware(mock_handler, kicked, data)

        mock_bot.mock.ban_chat_member.assert_not_awaited()

    async def test_blacklist_middleware_exception_handling(
        self,
        telegram_factory: TelegramObjectFactory,
        blacklist_middleware: BlacklistMiddleware,
        mock_user_repo: AsyncMock,
        mock_bot: MockBot,
    ):
        """Test middleware exception handling doesn't break the flow."""
        user = create_normal_user()
        chat = create_test_chat()
        message = telegram_factory.create_message(user=user, chat=chat)

        # Create handler that raises exception
        async def failing_handler(event, data):
            raise ValueError("Handler failed")

        data = {"user_repo": mock_user_repo, "bot": mock_bot.mock}

        mock_user_repo.get_blocked_users.return_value = []

        with pytest.raises(ValueError, match="Handler failed"):
            await blacklist_middleware(failing_handler, message, data)
