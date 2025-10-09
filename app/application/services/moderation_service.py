"""Moderation domain service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions

from app.core.logging import BotLogger
from app.domain.exceptions import TelegramApiException
from app.domain.value_objects import BlacklistPreview, ModerationAction, MuteDuration

if TYPE_CHECKING:
    from aiogram import Bot

    from app.application.services.spam import SpamService
    from app.domain.repositories import IChatRepository, IMessageRepository, IUserRepository


class ModerationService:
    """Moderation domain service."""

    def __init__(
        self,
        bot: Bot,
        chat_repository: IChatRepository,
        message_repository: IMessageRepository,
        user_repository: IUserRepository,
        spam_service: SpamService,
    ) -> None:
        self.bot = bot
        self.chat_repository = chat_repository
        self.message_repository = message_repository
        self.user_repository = user_repository
        self.spam_service = spam_service
        self.logger = BotLogger("moderation_service")

    async def mute_user(
        self,
        admin_id: int,
        user_id: int,
        chat_id: int,
        duration: MuteDuration,
        reason: str | None = None,
    ) -> None:
        """Mute user in a specific chat."""
        try:
            # Calculate until_date for mute
            import datetime

            until_date = datetime.datetime.now() + datetime.timedelta(seconds=duration.seconds)

            await self.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=until_date,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                ),
            )

            self.logger.log_moderation_action(
                admin_id=admin_id,
                target_user_id=user_id,
                action=ModerationAction.MUTE.value,
                chat_id=chat_id,
                reason=reason,
                duration=f"{duration.minutes}m",
            )

        except TelegramBadRequest as e:
            self.logger.log_telegram_error(
                operation="mute_user",
                error=str(e),
                chat_id=chat_id,
                user_id=user_id,
            )
            raise TelegramApiException("mute_user", str(e)) from e

    async def unmute_user(
        self,
        admin_id: int,
        user_id: int,
        chat_id: int,
        reason: str | None = None,
    ) -> None:
        """Unmute user in a specific chat."""
        try:
            # Restore default permissions
            from aiogram.types import ChatPermissions

            await self.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                ),
            )

            self.logger.log_moderation_action(
                admin_id=admin_id,
                target_user_id=user_id,
                action=ModerationAction.UNMUTE.value,
                chat_id=chat_id,
                reason=reason,
            )

        except TelegramBadRequest as e:
            self.logger.log_telegram_error(
                operation="unmute_user",
                error=str(e),
                chat_id=chat_id,
                user_id=user_id,
            )
            raise TelegramApiException("unmute_user", str(e)) from e

    async def ban_user(
        self,
        admin_id: int,
        user_id: int,
        chat_id: int,
        reason: str | None = None,
    ) -> None:
        """Ban user in a specific chat."""
        try:
            await self.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)

            self.logger.log_moderation_action(
                admin_id=admin_id,
                target_user_id=user_id,
                action=ModerationAction.BAN.value,
                chat_id=chat_id,
                reason=reason,
            )

        except TelegramBadRequest as e:
            self.logger.log_telegram_error(
                operation="ban_user",
                error=str(e),
                chat_id=chat_id,
                user_id=user_id,
            )
            raise TelegramApiException("ban_user", str(e)) from e

    async def unban_user(
        self,
        admin_id: int,
        user_id: int,
        chat_id: int,
        reason: str | None = None,
    ) -> None:
        """Unban user in a specific chat."""
        try:
            await self.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

            self.logger.log_moderation_action(
                admin_id=admin_id,
                target_user_id=user_id,
                action=ModerationAction.UNBAN.value,
                chat_id=chat_id,
                reason=reason,
            )

        except TelegramBadRequest as e:
            self.logger.log_telegram_error(
                operation="unban_user",
                error=str(e),
                chat_id=chat_id,
                user_id=user_id,
            )
            raise TelegramApiException("unban_user", str(e)) from e

    async def ban_user_globally(
        self,
        admin_id: int,
        user_id: int,
        reason: str | None = None,
    ) -> None:
        """Ban user in all chats."""
        chats = await self.chat_repository.get_all()
        for chat in chats:
            await self.ban_user(admin_id, user_id, chat.id, reason)

    async def unban_user_globally(
        self,
        admin_id: int,
        user_id: int,
        reason: str | None = None,
    ) -> None:
        """Unban user in all chats."""
        chats = await self.chat_repository.get_all()
        for chat in chats:
            await self.unban_user(admin_id, user_id, chat.id, reason)

    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> None:
        """Delete a message."""
        try:
            await self.bot.delete_message(chat_id, message_id)
        except TelegramBadRequest as e:
            self.logger.log_telegram_error(
                operation="delete_message",
                error=str(e),
                chat_id=chat_id,
            )
            raise TelegramApiException("delete_message", str(e)) from e

    async def _delete_user_messages(
        self,
        user_id: int,
        chat_id: int,
    ) -> None:
        """Delete all user messages in a specific chat."""
        messages = await self.message_repository.get_user_messages(user_id, chat_id)
        for message in messages:
            await self.delete_message(chat_id, message.message_id)

    async def build_blacklist_preview(
        self,
        user_id: int,
        chat_id: int,
        message_text: str | None,
    ) -> BlacklistPreview:
        """Collect statistics and heuristics for blacklist confirmation."""
        chats_count = await self.message_repository.count_user_chats(user_id)
        messages_count = await self.message_repository.count_user_messages(user_id)
        spam_detected = await self.spam_service.detect(chat_id=chat_id, user_id=user_id, text=message_text)

        return BlacklistPreview(
            chats_count=chats_count,
            messages_count=messages_count,
            spam_detected=spam_detected,
        )

    async def blacklist_user(
        self,
        user_id: int,
        *,
        source_chat_id: int | None = None,
        source_message_id: int | None = None,
        revoke_messages: bool = False,
        mark_spam: bool = False,
    ) -> None:
        """Block user across all managed chats and optionally clean history."""
        await self.user_repository.add_to_blacklist(user_id)

        if mark_spam and source_chat_id is not None and source_message_id is not None:
            await self.message_repository.label_spam(chat_id=source_chat_id, message_id=source_message_id)

        if source_chat_id is not None and source_message_id is not None:
            try:
                await self.bot.delete_message(chat_id=source_chat_id, message_id=source_message_id)
            except Exception as err:  # Telegram can fail for already removed messages
                self.logger.warning(
                    "Failed to delete message when blacklisting user",
                    user_id=user_id,
                    chat_id=source_chat_id,
                    message_id=source_message_id,
                    error=str(err),
                )

        chats = await self.chat_repository.get_all()
        for chat in chats:
            try:
                await self.bot.ban_chat_member(
                    chat_id=chat.id,
                    user_id=user_id,
                    revoke_messages=revoke_messages,
                )
            except Exception as err:
                self.logger.warning(
                    "Failed to ban user in chat during blacklist operation",
                    user_id=user_id,
                    chat_id=chat.id,
                    error=str(err),
                )

        if revoke_messages:
            user_messages = await self.message_repository.get_user_messages(user_id)
            for message in user_messages:
                try:
                    await self.bot.delete_message(
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                    )
                except Exception as err:
                    self.logger.warning(
                        "Failed to delete historical message during blacklist operation",
                        user_id=user_id,
                        chat_id=message.chat_id,
                        message_id=message.message_id,
                        error=str(err),
                    )

    async def remove_from_blacklist(self, user_id: int) -> None:
        """Remove user from blacklist and unban everywhere."""
        await self.user_repository.remove_from_blacklist(user_id)

        chats = await self.chat_repository.get_all()
        for chat in chats:
            try:
                await self.bot.unban_chat_member(chat_id=chat.id, user_id=user_id)
            except Exception as err:
                self.logger.warning(
                    "Failed to unban user during blacklist removal",
                    user_id=user_id,
                    chat_id=chat.id,
                    error=str(err),
                )
