"""Telegram testing helpers for simulating bot events and messages."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMember,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    Update,
    User,
)


class TelegramObjectFactory:
    """Factory for creating Telegram API objects for testing."""

    @staticmethod
    def create_user(
        id: int = 123456789,
        is_bot: bool = False,
        first_name: str = "Test",
        last_name: str | None = "User",
        username: str | None = "testuser",
        language_code: str | None = "en",
    ) -> User:
        """Create a mock Telegram User object."""
        return User(
            id=id,
            is_bot=is_bot,
            first_name=first_name,
            last_name=last_name,
            username=username,
            language_code=language_code,
        )

    @staticmethod
    def create_chat(
        id: int = -1001234567890,
        type: str = "supergroup",
        title: str | None = "Test Chat",
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        is_forum: bool | None = False,
    ) -> Chat:
        """Create a mock Telegram Chat object."""
        from aiogram.types import ChatPermissions

        # Default permissions for supergroups
        default_permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
        )

        return Chat(
            id=id,
            type=type,
            title=title,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_forum=is_forum,
            permissions=default_permissions,
        )

    @staticmethod
    def create_message(
        message_id: int = 42,
        user: User | None = None,
        chat: Chat | None = None,
        date: datetime | None = None,
        text: str | None = "Test message",
        reply_to_message: Message | None = None,
        entities: list[MessageEntity] | None = None,
        **kwargs,
    ) -> Message:
        """Create a mock Telegram Message object."""
        if user is None:
            user = TelegramObjectFactory.create_user()
        if chat is None:
            chat = TelegramObjectFactory.create_chat()
        if date is None:
            date = datetime.now(UTC)

        # Create message data
        message_data = {
            "message_id": message_id,
            "from_user": user,
            "chat": chat,
            "date": date,
            "text": text,
            "reply_to_message": reply_to_message,
            "entities": entities or [],
            **kwargs,
        }

        # Create mock message with proper attributes
        message = MagicMock(spec=Message)
        for key, value in message_data.items():
            setattr(message, key, value)

        # Add common methods
        message.answer = AsyncMock()
        message.reply = AsyncMock()
        message.delete = AsyncMock()
        message.edit_text = AsyncMock()
        message.edit_reply_markup = AsyncMock()

        return message

    @staticmethod
    def create_command_message(
        command: str, args: str = "", user: User | None = None, chat: Chat | None = None, **kwargs
    ) -> Message:
        """Create a message with a bot command."""
        text = f"/{command}"
        if args:
            text += f" {args}"

        # Create command entity
        entities = [MessageEntity(type="bot_command", offset=0, length=len(f"/{command}"))]

        return TelegramObjectFactory.create_message(text=text, user=user, chat=chat, entities=entities, **kwargs)

    @staticmethod
    def create_reply_message(
        text: str,
        replied_user: User | None = None,
        replying_user: User | None = None,
        chat: Chat | None = None,
        **kwargs,
    ) -> Message:
        """Create a message that replies to another message."""
        if replied_user is None:
            replied_user = TelegramObjectFactory.create_user(id=987654321, username="replieduser")

        reply_to_message = TelegramObjectFactory.create_message(user=replied_user, chat=chat, text="Original message")

        return TelegramObjectFactory.create_message(
            text=text, user=replying_user, chat=chat, reply_to_message=reply_to_message, **kwargs
        )

    @staticmethod
    def create_callback_query(
        id: str = "callback_123",
        user: User | None = None,
        message: Message | None = None,
        data: str | None = "test_callback",
        **kwargs,
    ) -> CallbackQuery:
        """Create a mock CallbackQuery object."""
        if user is None:
            user = TelegramObjectFactory.create_user()

        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.id = id
        callback_query.from_user = user
        callback_query.message = message
        callback_query.data = data
        callback_query.answer = AsyncMock()
        callback_query.edit_message_text = AsyncMock()
        callback_query.edit_message_reply_markup = AsyncMock()

        for key, value in kwargs.items():
            setattr(callback_query, key, value)

        return callback_query

    @staticmethod
    def create_chat_member_updated(
        chat: Chat | None = None,
        user: User | None = None,
        old_chat_member: ChatMember | None = None,
        new_chat_member: ChatMember | None = None,
        date: datetime | None = None,
        **kwargs,
    ) -> ChatMemberUpdated:
        """Create a ChatMemberUpdated event."""
        from aiogram.types import ChatMemberLeft, ChatMemberMember

        if chat is None:
            chat = TelegramObjectFactory.create_chat()
        if user is None:
            user = TelegramObjectFactory.create_user()
        if date is None:
            date = datetime.now(UTC)

        # Create default chat members if not provided
        if old_chat_member is None:
            old_chat_member = ChatMemberLeft(user=user, status="left")
        if new_chat_member is None:
            new_chat_member = ChatMemberMember(user=user, status="member")

        return ChatMemberUpdated(
            chat=chat,
            from_user=user,
            date=date,
            old_chat_member=old_chat_member,
            new_chat_member=new_chat_member,
            **kwargs,
        )

    @staticmethod
    def create_update(
        update_id: int = 123456,
        message: Message | None = None,
        callback_query: CallbackQuery | None = None,
        chat_member: ChatMemberUpdated | None = None,
        **kwargs,
    ) -> Update:
        """Create a mock Update object."""
        return Update(
            update_id=update_id, message=message, callback_query=callback_query, chat_member=chat_member, **kwargs
        )


class MockBot:
    """Mock Bot for testing handlers."""

    def __init__(self):
        self.mock = AsyncMock(spec=Bot)
        self._setup_methods()

    def _setup_methods(self):
        """Setup common bot methods."""
        self.mock.send_message = AsyncMock()
        self.mock.edit_message_text = AsyncMock()
        self.mock.delete_message = AsyncMock()
        self.mock.restrict_chat_member = AsyncMock()
        self.mock.ban_chat_member = AsyncMock()
        self.mock.unban_chat_member = AsyncMock()
        self.mock.get_chat_member = AsyncMock()
        self.mock.get_chat = AsyncMock()
        self.mock.answer_callback_query = AsyncMock()

    def __getattr__(self, name):
        return getattr(self.mock, name)


class HandlerTestContext:
    """Context manager for testing handlers with proper setup."""

    def __init__(self):
        self.bot = MockBot()
        self.session = AsyncMock()
        self.repositories = {}
        self.services = {}

    def add_repository(self, name: str, repository: Any):
        """Add a mock repository to the context."""
        self.repositories[name] = repository

    def add_service(self, name: str, service: Any):
        """Add a mock service to the context."""
        self.services[name] = service

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TelegramEventSimulator:
    """Simulator for complex Telegram events and workflows."""

    def __init__(self, context: HandlerTestContext):
        self.context = context
        self.factory = TelegramObjectFactory()

    async def simulate_user_join(
        self, user: User | None = None, chat: Chat | None = None, inviter: User | None = None
    ) -> ChatMemberUpdated:
        """Simulate a user joining a chat."""
        if user is None:
            user = self.factory.create_user()
        if chat is None:
            chat = self.factory.create_chat()
        if inviter is None:
            inviter = self.factory.create_user(id=999999999, username="inviter")

        return self.factory.create_chat_member_updated(
            chat=chat,
            user=inviter,
            old_chat_member=ChatMemberLeft(user=user),
            new_chat_member=ChatMemberMember(user=user),
        )

    async def simulate_user_leave(self, user: User | None = None, chat: Chat | None = None) -> ChatMemberUpdated:
        """Simulate a user leaving a chat."""
        if user is None:
            user = self.factory.create_user()
        if chat is None:
            chat = self.factory.create_chat()

        return self.factory.create_chat_member_updated(
            chat=chat, user=user, old_chat_member=ChatMemberMember(user=user), new_chat_member=ChatMemberLeft(user=user)
        )

    async def simulate_moderation_action(
        self,
        action: str,
        admin: User | None = None,
        target_user: User | None = None,
        chat: Chat | None = None,
        args: str = "",
    ) -> Message:
        """Simulate a moderation command."""
        if admin is None:
            admin = self.factory.create_user(id=888888888, username="admin")
        if target_user is None:
            target_user = self.factory.create_user(id=777777777, username="target")
        if chat is None:
            chat = self.factory.create_chat()

        return self.factory.create_reply_message(
            text=f"/{action} {args}".strip(), replied_user=target_user, replying_user=admin, chat=chat
        )

    async def simulate_button_click(
        self, callback_data: str, user: User | None = None, message: Message | None = None
    ) -> CallbackQuery:
        """Simulate clicking an inline keyboard button."""
        if user is None:
            user = self.factory.create_user()

        return self.factory.create_callback_query(data=callback_data, user=user, message=message)


# Utility functions for common test scenarios
def create_admin_user(id: int = 888888888) -> User:
    """Create a user that should be treated as admin."""
    return TelegramObjectFactory.create_user(id=id, username="admin_user", first_name="Admin", last_name="User")


def create_normal_user(
    id: int = 123456789,
    username: str = "normal_user",
    first_name: str = "Normal",
    last_name: str = "User",
    **kwargs,
) -> User:
    """Create a normal user."""
    return TelegramObjectFactory.create_user(
        id=id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        **kwargs,
    )


def create_test_chat(id: int = -1001234567890) -> Chat:
    """Create a test supergroup chat."""
    return TelegramObjectFactory.create_chat(id=id, title="Test Supergroup", type="supergroup")


def create_inline_keyboard(buttons: list[list[dict[str, str]]]) -> InlineKeyboardMarkup:
    """Create an inline keyboard markup."""
    keyboard = []
    for row in buttons:
        keyboard_row = []
        for button in row:
            keyboard_row.append(InlineKeyboardButton(text=button["text"], callback_data=button.get("callback_data")))
        keyboard.append(keyboard_row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Pytest fixtures for easy use
import pytest


@pytest.fixture
def telegram_factory():
    """Provide TelegramObjectFactory for tests."""
    return TelegramObjectFactory()


@pytest.fixture
def mock_bot():
    """Provide MockBot for tests."""
    return MockBot()


@pytest.fixture
def handler_context():
    """Provide HandlerTestContext for tests."""
    return HandlerTestContext()


@pytest.fixture
async def event_simulator(handler_context):
    """Provide TelegramEventSimulator for tests."""
    return TelegramEventSimulator(handler_context)


@pytest.fixture
def admin_user():
    """Provide an admin user for tests."""
    return create_admin_user()


@pytest.fixture
def normal_user():
    """Provide a normal user for tests."""
    return create_normal_user()


@pytest.fixture
def test_chat():
    """Provide a test chat for tests."""
    return create_test_chat()
