"""Unit tests for TelethonClient wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.config import TelethonSettings
from app.telethon.telethon_client import (
    ChatInfo,
    ChatMember,
    MessageInfo,
    TelethonClient,
    UserInfo,
)


@pytest.fixture
def disabled_settings():
    """TelethonSettings with enabled=False."""
    return TelethonSettings(
        api_id=12345,
        api_hash="test_hash",
        session_name="test_session",
        enabled=False,
        phone=None,
    )


@pytest.fixture
def enabled_settings():
    """TelethonSettings with enabled=True."""
    return TelethonSettings(
        api_id=12345,
        api_hash="test_hash",
        session_name="test_session",
        enabled=True,
        phone="+1234567890",
    )


@pytest.fixture
def mock_telegram_client():
    """Mock Telethon TelegramClient."""
    client = AsyncMock()
    client.start = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def telethon_client_disabled(disabled_settings):
    """TelethonClient in disabled state."""
    return TelethonClient(settings=disabled_settings)


@pytest.fixture
def telethon_client_enabled(enabled_settings, mock_telegram_client):
    """TelethonClient in enabled+connected state with mocked underlying client."""
    tc = TelethonClient(settings=enabled_settings)
    tc._client = mock_telegram_client
    tc._connected = True
    return tc


# --- Initialization tests ---


class TestInitialization:
    def test_disabled_client_not_available(self, telethon_client_disabled):
        assert not telethon_client_disabled.is_available
        assert telethon_client_disabled._client is None
        assert not telethon_client_disabled._connected

    def test_enabled_connected_client_is_available(self, telethon_client_enabled):
        assert telethon_client_enabled.is_available

    def test_enabled_but_not_connected_is_not_available(self, enabled_settings):
        tc = TelethonClient(settings=enabled_settings)
        assert not tc.is_available


# --- Lifecycle tests ---


class TestLifecycle:
    async def test_start_disabled_is_noop(self, telethon_client_disabled):
        await telethon_client_disabled.start()
        assert not telethon_client_disabled._connected
        assert telethon_client_disabled._client is None

    async def test_start_enabled_connects(self, enabled_settings, mock_telegram_client):
        tc = TelethonClient(settings=enabled_settings)
        with patch.object(tc, "_create_client", return_value=mock_telegram_client):
            await tc.start()
        assert tc._connected
        assert tc._client is mock_telegram_client
        mock_telegram_client.start.assert_awaited_once_with(phone="+1234567890")

    async def test_start_failure_sets_not_connected(self, enabled_settings, mock_telegram_client):
        mock_telegram_client.start.side_effect = ConnectionError("network down")
        tc = TelethonClient(settings=enabled_settings)
        with patch.object(tc, "_create_client", return_value=mock_telegram_client):
            with pytest.raises(ConnectionError):
                await tc.start()
        assert not tc._connected

    async def test_stop_disconnects(self, telethon_client_enabled, mock_telegram_client):
        await telethon_client_enabled.stop()
        mock_telegram_client.disconnect.assert_awaited_once()
        assert not telethon_client_enabled._connected
        assert telethon_client_enabled._client is None

    async def test_stop_when_not_started_is_safe(self, telethon_client_disabled):
        # Should not raise
        await telethon_client_disabled.stop()

    async def test_stop_handles_disconnect_error(self, telethon_client_enabled, mock_telegram_client):
        mock_telegram_client.disconnect.side_effect = RuntimeError("disconnect failed")
        await telethon_client_enabled.stop()
        # Should still clean up
        assert not telethon_client_enabled._connected
        assert telethon_client_enabled._client is None


# --- Disabled state no-op tests ---


class TestDisabledNoOp:
    """All data methods should return empty results when disabled."""

    @pytest.mark.parametrize(
        ("method", "args", "expected"),
        [
            ("get_chat_history", (123,), []),
            ("get_user_info", (123,), None),
            ("get_chat_members", (123,), []),
            ("get_chat_info", (123,), None),
            ("search_messages", (123, "test"), []),
            ("forward_messages", (123, 456, [1, 2]), []),
            ("create_supergroup", ("Test Group",), None),
            ("add_chat_admin", (123, 456), False),
            ("invite_to_chat", (123, 456), False),
            ("send_message", (123, "hello"), None),
        ],
    )
    async def test_disabled_returns_empty(self, telethon_client_disabled, method, args, expected):
        result = await getattr(telethon_client_disabled, method)(*args)
        assert result == expected


# --- FloodWait retry logic tests ---


class TestFloodWaitRetry:
    async def test_flood_wait_retries_and_succeeds(self, telethon_client_enabled):
        """FloodWaitError should trigger a wait and retry."""
        # Create a mock FloodWaitError
        flood_error = MagicMock()
        flood_error.seconds = 0  # 0 seconds wait for fast test

        call_count = 0

        async def _factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                exc = type("FloodWaitError", (Exception,), {"seconds": 0})()
                # We need to use the real import path
                raise exc
            return "success"

        # Patch FloodWaitError in the module
        mock_flood_cls = type("FloodWaitError", (Exception,), {"seconds": 0})

        with patch(
            "app.telethon.telethon_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with patch("telethon.errors.FloodWaitError", mock_flood_cls):
                result = await telethon_client_enabled._execute_with_flood_wait(_factory, max_retries=3, base_delay=0.0)
        assert result == "success"

    async def test_retries_exhausted_raises(self, telethon_client_enabled):
        """When all retries are exhausted, the last exception should be raised."""
        error = ValueError("persistent error")

        async def _factory():
            raise error

        with patch(
            "app.telethon.telethon_client.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
                with pytest.raises(ValueError, match="persistent error"):
                    await telethon_client_enabled._execute_with_flood_wait(_factory, max_retries=2, base_delay=0.0)

    async def test_succeeds_on_first_try(self, telethon_client_enabled):
        """No retries needed when operation succeeds immediately."""

        async def _factory():
            return 42

        with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
            result = await telethon_client_enabled._execute_with_flood_wait(_factory)
        assert result == 42


# --- Data method tests (with mocked client) ---


class TestGetChatHistory:
    async def test_returns_message_info_list(self, telethon_client_enabled, mock_telegram_client):
        mock_msg = MagicMock()
        mock_msg.id = 1
        mock_msg.sender_id = 100
        mock_msg.text = "hello"
        mock_msg.date = "2024-01-01"
        mock_msg.reply_to = None
        mock_msg.reply_to_msg_id = None

        async def fake_iter(*args, **kwargs):
            yield mock_msg

        mock_telegram_client.iter_messages = fake_iter

        with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
            result = await telethon_client_enabled.get_chat_history(chat_id=123, limit=10)

        assert len(result) == 1
        assert isinstance(result[0], MessageInfo)
        assert result[0].message_id == 1
        assert result[0].text == "hello"
        assert result[0].chat_id == 123


class TestGetUserInfo:
    async def test_returns_user_info(self, telethon_client_enabled, mock_telegram_client):
        mock_user = MagicMock()
        mock_user.id = 100
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.username = "johndoe"
        mock_user.phone = None
        mock_user.bot = False
        mock_user.premium = True

        mock_full = MagicMock()
        mock_full.users = [mock_user]
        mock_full.full_user.about = "Test bio"

        mock_photos = MagicMock()
        mock_photos.count = 3

        # The client is called like client(Request)
        call_results = [mock_full, mock_photos]
        call_idx = 0

        async def mock_call(request):
            nonlocal call_idx
            result = call_results[call_idx]
            call_idx += 1
            return result

        mock_telegram_client.side_effect = mock_call

        with (
            patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})),
            patch("telethon.tl.functions.users.GetFullUserRequest"),
            patch("telethon.tl.functions.photos.GetUserPhotosRequest"),
        ):
            result = await telethon_client_enabled.get_user_info(user_id=100)

        assert result is not None
        assert isinstance(result, UserInfo)
        assert result.user_id == 100
        assert result.first_name == "John"
        assert result.bio == "Test bio"
        assert result.is_premium is True
        assert result.photo_count == 3


class TestGetChatMembers:
    async def test_returns_member_list(self, telethon_client_enabled, mock_telegram_client):
        mock_participant = MagicMock()
        mock_participant.id = 200
        mock_participant.first_name = "Jane"
        mock_participant.last_name = "Smith"
        mock_participant.username = "janesmith"

        async def fake_iter(*args, **kwargs):
            yield mock_participant

        mock_telegram_client.iter_participants = fake_iter

        with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
            result = await telethon_client_enabled.get_chat_members(chat_id=123)

        assert len(result) == 1
        assert isinstance(result[0], ChatMember)
        assert result[0].user_id == 200
        assert result[0].username == "janesmith"


class TestSearchMessages:
    async def test_returns_matching_messages(self, telethon_client_enabled, mock_telegram_client):
        mock_msg = MagicMock()
        mock_msg.id = 5
        mock_msg.sender_id = 100
        mock_msg.text = "search result"
        mock_msg.date = None
        mock_msg.reply_to = None

        async def fake_iter(*args, **kwargs):
            yield mock_msg

        mock_telegram_client.iter_messages = fake_iter

        with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
            result = await telethon_client_enabled.search_messages(123, "search")

        assert len(result) == 1
        assert result[0].text == "search result"


class TestForwardMessages:
    async def test_forwards_and_returns_info(self, telethon_client_enabled, mock_telegram_client):
        mock_msg = MagicMock()
        mock_msg.id = 10
        mock_msg.sender_id = 100
        mock_msg.text = "forwarded"
        mock_msg.date = None
        mock_msg.reply_to = None

        mock_telegram_client.forward_messages = AsyncMock(return_value=[mock_msg])

        with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
            result = await telethon_client_enabled.forward_messages(from_chat=123, to_chat=456, message_ids=[1])

        assert len(result) == 1
        assert result[0].message_id == 10
        assert result[0].chat_id == 456


class TestNotConnectedNoOp:
    """Methods should return empty results when enabled but not connected."""

    @pytest.mark.parametrize(
        ("method", "args", "expected"),
        [
            ("create_supergroup", ("Test",), None),
            ("add_chat_admin", (123, 456), False),
            ("invite_to_chat", (123, 456), False),
            ("send_message", (123, "hello"), None),
        ],
    )
    async def test_not_connected_returns_empty(self, enabled_settings, method, args, expected):
        tc = TelethonClient(settings=enabled_settings)
        result = await getattr(tc, method)(*args)
        assert result == expected


class TestCreateSupergroup:
    async def test_creates_and_returns_chat_info(self, telethon_client_enabled, mock_telegram_client):
        mock_chat = MagicMock()
        mock_chat.id = 999
        mock_chat.title = "New Group"
        mock_chat.username = None

        mock_result = MagicMock()
        mock_result.chats = [mock_chat]

        mock_telegram_client.side_effect = AsyncMock(return_value=mock_result)

        with (
            patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})),
            patch("telethon.tl.functions.channels.CreateChannelRequest"),
        ):
            result = await telethon_client_enabled.create_supergroup("New Group", about="desc")

        assert result is not None
        assert isinstance(result, ChatInfo)
        assert result.chat_id == 999
        assert result.title == "New Group"
        assert result.is_channel is False


class TestAddChatAdmin:
    async def test_success_returns_true(self, telethon_client_enabled, mock_telegram_client):
        mock_telegram_client.side_effect = AsyncMock(return_value=MagicMock())

        with (
            patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})),
            patch("telethon.tl.functions.channels.EditAdminRequest"),
            patch("telethon.tl.types.ChatAdminRights"),
        ):
            result = await telethon_client_enabled.add_chat_admin(123, 456, title="mod")

        assert result is True

    async def test_failure_returns_false(self, telethon_client_enabled, mock_telegram_client):
        mock_telegram_client.side_effect = RuntimeError("permission denied")

        with (
            patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})),
            patch("telethon.tl.functions.channels.EditAdminRequest"),
            patch("telethon.tl.types.ChatAdminRights"),
            patch(
                "app.telethon.telethon_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await telethon_client_enabled.add_chat_admin(123, 456)

        assert result is False


class TestInviteToChat:
    async def test_success_returns_true(self, telethon_client_enabled, mock_telegram_client):
        mock_telegram_client.side_effect = AsyncMock(return_value=MagicMock())

        with (
            patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})),
            patch("telethon.tl.functions.channels.InviteToChannelRequest"),
        ):
            result = await telethon_client_enabled.invite_to_chat(123, 456)

        assert result is True

    async def test_failure_returns_false(self, telethon_client_enabled, mock_telegram_client):
        mock_telegram_client.side_effect = RuntimeError("user not found")

        with (
            patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})),
            patch("telethon.tl.functions.channels.InviteToChannelRequest"),
            patch(
                "app.telethon.telethon_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await telethon_client_enabled.invite_to_chat(123, 456)

        assert result is False


class TestSendMessage:
    async def test_sends_and_returns_message_info(self, telethon_client_enabled, mock_telegram_client):
        mock_msg = MagicMock()
        mock_msg.id = 42
        mock_msg.sender_id = 100
        mock_msg.text = "hello world"
        mock_msg.date = "2024-01-01"

        mock_telegram_client.send_message = AsyncMock(return_value=mock_msg)

        with patch("telethon.errors.FloodWaitError", type("FWE", (Exception,), {"seconds": 0})):
            result = await telethon_client_enabled.send_message(123, "hello world")

        assert result is not None
        assert isinstance(result, MessageInfo)
        assert result.message_id == 42
        assert result.chat_id == 123
        assert result.text == "hello world"
