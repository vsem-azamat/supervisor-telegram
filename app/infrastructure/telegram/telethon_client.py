"""Telethon client wrapper for Telegram Client API features.

This module provides a high-level wrapper around Telethon's TelegramClient,
enabling userbot/client API features that the Bot API cannot provide
(e.g., reading full chat history, getting user bios, searching messages).

This is NOT a replacement for aiogram -- it runs alongside the bot for
supplementary data-fetching capabilities.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import Channel, Chat, Message, User

    from app.core.config import TelethonSettings

logger = get_logger("telethon_client")

# Default retry parameters for FloodWait handling
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 1.0
_FLOOD_WAIT_BUFFER_SECONDS = 1


@dataclass
class UserInfo:
    """Structured user information from Telethon."""

    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    phone: str | None = None
    bio: str | None = None
    is_bot: bool = False
    is_premium: bool = False
    photo_count: int = 0


@dataclass
class ChatInfo:
    """Structured chat information from Telethon."""

    chat_id: int
    title: str | None = None
    description: str | None = None
    member_count: int | None = None
    username: str | None = None
    linked_chat_id: int | None = None
    is_channel: bool = False


@dataclass
class ChatMember:
    """Structured chat member information."""

    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


@dataclass
class MessageInfo:
    """Structured message information from Telethon."""

    message_id: int
    chat_id: int
    sender_id: int | None = None
    text: str | None = None
    date: Any = None
    reply_to_msg_id: int | None = None


@dataclass
class TelethonClient:
    """High-level wrapper around Telethon's TelegramClient.

    Provides async methods for Client API features that Bot API cannot do:
    - Full message history retrieval
    - User bio and profile photo access
    - Chat member enumeration
    - Message search within chats
    - Message forwarding

    All methods are no-ops when the client is disabled or not connected.
    FloodWait errors are handled automatically with exponential backoff.
    """

    settings: TelethonSettings
    _client: TelegramClient | None = field(default=None, init=False, repr=False)
    _connected: bool = field(default=False, init=False)

    def _create_client(self) -> TelegramClient:
        """Create the underlying TelegramClient instance."""
        from telethon import TelegramClient

        return TelegramClient(
            self.settings.session_name,
            self.settings.api_id,
            self.settings.api_hash,
        )

    @property
    def is_available(self) -> bool:
        """Check if the client is enabled and connected."""
        return self.settings.enabled and self._connected

    async def start(self) -> None:
        """Connect and start the Telethon client.

        Does nothing if the client is disabled in settings.
        For first-time auth, settings.phone must be provided
        and interactive terminal access is required.
        """
        if not self.settings.enabled:
            logger.info("Telethon client disabled, skipping start")
            return

        try:
            self._client = self._create_client()
            await self._client.start(phone=self.settings.phone)
            self._connected = True
            logger.info("Telethon client started successfully")
        except Exception:
            logger.error("Failed to start Telethon client", exc_info=True)
            self._connected = False
            raise

    async def stop(self) -> None:
        """Disconnect the Telethon client gracefully."""
        if self._client is not None:
            try:
                await self._client.disconnect()
                logger.info("Telethon client disconnected")
            except Exception:
                logger.error("Error disconnecting Telethon client", exc_info=True)
            finally:
                self._connected = False
                self._client = None

    async def _execute_with_flood_wait(
        self,
        coro_factory: Any,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        base_delay: float = _DEFAULT_BASE_DELAY,
    ) -> Any:
        """Execute an async operation with FloodWait retry logic.

        Uses exponential backoff. If a FloodWaitError is raised by Telethon,
        waits for the required duration plus a small buffer, then retries.

        Args:
            coro_factory: A callable that returns a coroutine (called on each retry).
            max_retries: Maximum number of retry attempts.
            base_delay: Base delay in seconds for exponential backoff on non-flood errors.

        Returns:
            The result of the coroutine.

        Raises:
            The last exception if all retries are exhausted.
        """
        from telethon.errors import FloodWaitError

        last_exception: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await coro_factory()
            except FloodWaitError as e:
                wait_time = e.seconds + _FLOOD_WAIT_BUFFER_SECONDS
                logger.warning(
                    "FloodWait hit, waiting",
                    wait_seconds=wait_time,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
                await asyncio.sleep(wait_time)
                last_exception = e
            except Exception as e:
                # Don't retry on non-transient errors (entity not found, auth, etc.)
                err_str = str(e)
                non_transient = ("Could not find the input entity", "No user has", "AuthKey", "not found")
                if any(marker in err_str for marker in non_transient):
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Telethon request failed, retrying",
                    error=err_str,
                    attempt=attempt + 1,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                last_exception = e

        if last_exception is not None:
            raise last_exception
        msg = "No retries were attempted"
        raise RuntimeError(msg)

    async def get_chat_history(
        self,
        chat_id: int,
        limit: int = 100,
    ) -> list[MessageInfo]:
        """Retrieve message history from a chat.

        Args:
            chat_id: The chat/channel/group ID.
            limit: Maximum number of messages to retrieve.

        Returns:
            List of MessageInfo objects, newest first.
        """
        if not self.is_available or self._client is None:
            return []

        async def _fetch() -> list[Message]:
            assert self._client is not None  # noqa: S101
            return [msg async for msg in self._client.iter_messages(chat_id, limit=limit)]

        messages: list[Message] = await self._execute_with_flood_wait(_fetch)
        return [
            MessageInfo(
                message_id=msg.id,
                chat_id=chat_id,
                sender_id=msg.sender_id,
                text=msg.text,
                date=msg.date,
                reply_to_msg_id=msg.reply_to_msg_id if msg.reply_to else None,
            )
            for msg in messages
        ]

    async def get_user_info(self, user_id: int) -> UserInfo | None:
        """Get full user information including bio and photo count.

        Args:
            user_id: Telegram user ID.

        Returns:
            UserInfo object or None if unavailable.
        """
        if not self.is_available or self._client is None:
            return None

        from telethon.tl.functions.photos import GetUserPhotosRequest
        from telethon.tl.functions.users import GetFullUserRequest

        async def _fetch() -> tuple[Any, Any]:
            assert self._client is not None  # noqa: S101
            full = await self._client(GetFullUserRequest(user_id))
            photos = await self._client(GetUserPhotosRequest(user_id=user_id, offset=0, max_id=0, limit=1))
            return full, photos

        full_user, photos = await self._execute_with_flood_wait(_fetch)
        user: User = full_user.users[0]
        return UserInfo(
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            phone=user.phone,
            bio=full_user.full_user.about,
            is_bot=user.bot or False,
            is_premium=user.premium or False,
            photo_count=photos.count if hasattr(photos, "count") else len(photos.photos),
        )

    async def get_chat_members(
        self,
        chat_id: int,
        limit: int = 200,
    ) -> list[ChatMember]:
        """List members of a chat/group/channel.

        Args:
            chat_id: The chat ID.
            limit: Maximum number of members to retrieve.

        Returns:
            List of ChatMember objects.
        """
        if not self.is_available or self._client is None:
            return []

        async def _fetch() -> list[Any]:
            assert self._client is not None  # noqa: S101
            return [p async for p in self._client.iter_participants(chat_id, limit=limit)]

        participants = await self._execute_with_flood_wait(_fetch)
        return [
            ChatMember(
                user_id=p.id,
                first_name=p.first_name,
                last_name=p.last_name,
                username=p.username,
            )
            for p in participants
        ]

    async def get_chat_info(self, chat_id: int) -> ChatInfo | None:
        """Get full chat information including description and linked chats.

        Args:
            chat_id: The chat ID.

        Returns:
            ChatInfo object or None if unavailable.
        """
        if not self.is_available or self._client is None:
            return None

        async def _fetch() -> tuple[Any, Any]:
            assert self._client is not None  # noqa: S101
            entity = await self._client.get_entity(chat_id)
            full = await self._client(_get_full_chat_request(entity))
            return entity, full

        entity, full = await self._execute_with_flood_wait(_fetch)
        return _build_chat_info(entity, full)

    async def search_messages(
        self,
        chat_id: int,
        query: str,
        limit: int = 50,
    ) -> list[MessageInfo]:
        """Search for messages in a chat.

        Args:
            chat_id: The chat ID to search in.
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching MessageInfo objects.
        """
        if not self.is_available or self._client is None:
            return []

        async def _fetch() -> list[Message]:
            assert self._client is not None  # noqa: S101
            return [msg async for msg in self._client.iter_messages(chat_id, search=query, limit=limit)]

        messages: list[Message] = await self._execute_with_flood_wait(_fetch)
        return [
            MessageInfo(
                message_id=msg.id,
                chat_id=chat_id,
                sender_id=msg.sender_id,
                text=msg.text,
                date=msg.date,
                reply_to_msg_id=msg.reply_to_msg_id if msg.reply_to else None,
            )
            for msg in messages
        ]

    async def create_supergroup(self, title: str, about: str = "") -> ChatInfo | None:
        """Create a new supergroup (megagroup).

        Args:
            title: The title for the new supergroup.
            about: Optional description for the supergroup.

        Returns:
            ChatInfo object with the new group's info, or None if unavailable.
        """
        if not self.is_available or self._client is None:
            return None

        from telethon.tl.functions.channels import CreateChannelRequest

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            return await self._client(CreateChannelRequest(title=title, about=about, megagroup=True))

        logger.info("Creating supergroup", title=title)
        result = await self._execute_with_flood_wait(_fetch)
        chat = result.chats[0]
        return ChatInfo(
            chat_id=chat.id,
            title=chat.title,
            username=getattr(chat, "username", None),
            is_channel=False,
        )

    async def add_chat_admin(self, chat_id: int, user_id: int, title: str = "") -> bool:
        """Promote a user to admin in a chat.

        Args:
            chat_id: The chat ID.
            user_id: The user ID to promote.
            title: Optional custom admin title.

        Returns:
            True on success, False on failure.
        """
        if not self.is_available or self._client is None:
            return False

        from telethon.tl.functions.channels import EditAdminRequest
        from telethon.tl.types import ChatAdminRights

        admin_rights = ChatAdminRights(
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            manage_call=True,
        )

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            return await self._client(
                EditAdminRequest(
                    channel=chat_id,
                    user_id=user_id,
                    admin_rights=admin_rights,
                    rank=title,
                )
            )

        logger.info("Adding chat admin", chat_id=chat_id, user_id=user_id)
        try:
            await self._execute_with_flood_wait(_fetch)
            return True
        except Exception:
            logger.error("Failed to add chat admin", chat_id=chat_id, user_id=user_id, exc_info=True)
            return False

    async def invite_to_chat(self, chat_id: int, user_id: int) -> bool:
        """Invite a user to a chat.

        Args:
            chat_id: The chat ID.
            user_id: The user ID to invite.

        Returns:
            True on success, False on failure.
        """
        if not self.is_available or self._client is None:
            return False

        from telethon.tl.functions.channels import InviteToChannelRequest

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            return await self._client(InviteToChannelRequest(channel=chat_id, users=[user_id]))

        logger.info("Inviting user to chat", chat_id=chat_id, user_id=user_id)
        try:
            await self._execute_with_flood_wait(_fetch)
            return True
        except Exception:
            logger.error("Failed to invite user to chat", chat_id=chat_id, user_id=user_id, exc_info=True)
            return False

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "html") -> MessageInfo | None:
        """Send a message to a chat.

        Args:
            chat_id: The chat ID.
            text: Message text to send.
            parse_mode: Parse mode for the message (default "html").

        Returns:
            MessageInfo object on success, or None if unavailable.
        """
        if not self.is_available or self._client is None:
            return None

        async def _fetch() -> Message:
            assert self._client is not None  # noqa: S101
            return await self._client.send_message(chat_id, text, parse_mode=parse_mode)

        logger.info("Sending message", chat_id=chat_id)
        msg: Message = await self._execute_with_flood_wait(_fetch)
        return MessageInfo(
            message_id=msg.id,
            chat_id=chat_id,
            sender_id=msg.sender_id,
            text=msg.text,
            date=msg.date,
        )

    async def send_scheduled_message(
        self,
        chat_id: int,
        text: str,
        schedule_date: Any,
        *,
        parse_mode: str = "html",
    ) -> MessageInfo | None:
        """Send a message scheduled for future delivery via Client API.

        Returns MessageInfo with the scheduled message ID, or None.
        """
        if not self.is_available or self._client is None:
            return None

        async def _fetch() -> Message:
            assert self._client is not None  # noqa: S101
            return await self._client.send_message(
                chat_id,
                text,
                parse_mode=parse_mode,
                schedule=schedule_date,
            )

        logger.info("Sending scheduled message", chat_id=chat_id, schedule=str(schedule_date))
        msg: Message = await self._execute_with_flood_wait(_fetch)
        return MessageInfo(
            message_id=msg.id,
            chat_id=chat_id,
            sender_id=msg.sender_id,
            text=msg.text,
            date=msg.date,
        )

    async def send_scheduled_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str,
        schedule_date: Any,
        *,
        parse_mode: str = "html",
    ) -> MessageInfo | None:
        """Send a photo scheduled for future delivery."""
        if not self.is_available or self._client is None:
            return None

        async def _fetch() -> Message:
            assert self._client is not None  # noqa: S101
            return await self._client.send_file(
                chat_id,
                photo,
                caption=caption,
                parse_mode=parse_mode,
                schedule=schedule_date,
            )

        logger.info("Sending scheduled photo", chat_id=chat_id, schedule=str(schedule_date))
        msg: Message = await self._execute_with_flood_wait(_fetch)
        return MessageInfo(
            message_id=msg.id,
            chat_id=chat_id,
            sender_id=msg.sender_id,
            text=msg.text,
            date=msg.date,
        )

    async def edit_scheduled_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        parse_mode: str = "md",
    ) -> bool:
        """Edit a scheduled (not yet delivered) message."""
        if not self.is_available or self._client is None:
            return False

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            entity = await self._client.get_input_entity(chat_id)
            from telethon.tl.functions.messages import EditMessageRequest

            # Parse formatting entities from text
            parsed_text, entities = await self._client._parse_message_text(text, parse_mode)

            return await self._client(
                EditMessageRequest(
                    peer=entity,
                    id=message_id,
                    message=parsed_text,
                    entities=entities,
                    schedule_date=None,  # keep existing schedule
                )
            )

        try:
            await self._execute_with_flood_wait(_fetch)
            return True
        except Exception:
            logger.error("Failed to edit scheduled message", chat_id=chat_id, message_id=message_id, exc_info=True)
            return False

    async def delete_scheduled_messages(
        self,
        chat_id: int,
        message_ids: list[int],
    ) -> bool:
        """Delete scheduled messages before they are delivered."""
        if not self.is_available or self._client is None:
            return False

        from telethon.tl.functions.messages import DeleteScheduledMessagesRequest

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            entity = await self._client.get_input_entity(chat_id)
            return await self._client(
                DeleteScheduledMessagesRequest(
                    peer=entity,
                    id=message_ids,
                )
            )

        try:
            await self._execute_with_flood_wait(_fetch)
            return True
        except Exception:
            logger.error("Failed to delete scheduled messages", chat_id=chat_id, ids=message_ids, exc_info=True)
            return False

    async def get_scheduled_messages(
        self,
        chat_id: int,
    ) -> list[MessageInfo]:
        """List all currently scheduled messages for a chat."""
        if not self.is_available or self._client is None:
            return []

        from telethon.tl.functions.messages import GetScheduledHistoryRequest

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            entity = await self._client.get_input_entity(chat_id)
            return await self._client(GetScheduledHistoryRequest(peer=entity, hash=0))

        result = await self._execute_with_flood_wait(_fetch)
        return [
            MessageInfo(
                message_id=msg.id,
                chat_id=chat_id,
                sender_id=getattr(msg, "from_id", None) and getattr(msg.from_id, "user_id", None),
                text=msg.message,
                date=msg.date,
            )
            for msg in result.messages
        ]

    async def send_scheduled_messages_now(
        self,
        chat_id: int,
        message_ids: list[int],
    ) -> bool:
        """Force-send scheduled messages immediately."""
        if not self.is_available or self._client is None:
            return False

        from telethon.tl.functions.messages import SendScheduledMessagesRequest

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            entity = await self._client.get_input_entity(chat_id)
            return await self._client(
                SendScheduledMessagesRequest(
                    peer=entity,
                    id=message_ids,
                )
            )

        try:
            await self._execute_with_flood_wait(_fetch)
            return True
        except Exception:
            logger.error("Failed to send scheduled messages now", chat_id=chat_id, ids=message_ids, exc_info=True)
            return False

    async def forward_messages(
        self,
        from_chat: int,
        to_chat: int,
        message_ids: list[int],
    ) -> list[MessageInfo]:
        """Forward messages between chats.

        Args:
            from_chat: Source chat ID.
            to_chat: Destination chat ID.
            message_ids: List of message IDs to forward.

        Returns:
            List of forwarded MessageInfo objects.
        """
        if not self.is_available or self._client is None:
            return []

        async def _fetch() -> Any:
            assert self._client is not None  # noqa: S101
            return await self._client.forward_messages(to_chat, message_ids, from_chat)

        raw_result: Any = await self._execute_with_flood_wait(_fetch)
        result: list[Any] = raw_result if isinstance(raw_result, list) else [raw_result]
        return [
            MessageInfo(
                message_id=msg.id,
                chat_id=to_chat,
                sender_id=msg.sender_id,
                text=msg.text,
                date=msg.date,
                reply_to_msg_id=msg.reply_to_msg_id if msg.reply_to else None,
            )
            for msg in result
        ]


def _get_full_chat_request(entity: Channel | Chat | Any) -> Any:
    """Get the appropriate 'get full chat' request for the entity type."""
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.tl.functions.messages import GetFullChatRequest
    from telethon.tl.types import Channel

    if isinstance(entity, Channel):
        return GetFullChannelRequest(entity)
    return GetFullChatRequest(entity.id)


def _build_chat_info(entity: Any, full: Any) -> ChatInfo:
    """Build a ChatInfo from Telethon entity and full chat response."""
    from telethon.tl.types import Channel

    is_channel = isinstance(entity, Channel)
    full_chat = full.full_chat

    return ChatInfo(
        chat_id=entity.id,
        title=getattr(entity, "title", None),
        description=getattr(full_chat, "about", None),
        member_count=getattr(full_chat, "participants_count", None),
        username=getattr(entity, "username", None),
        linked_chat_id=getattr(full_chat, "linked_chat_id", None),
        is_channel=is_channel,
    )
