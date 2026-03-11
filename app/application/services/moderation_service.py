"""Moderation domain service."""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions

from app.core.logging import BotLogger
from app.domain.exceptions import TelegramApiException
from app.domain.repositories import IChatRepository, IMessageRepository
from app.domain.value_objects import ModerationAction, MuteDuration


class ModerationService:
    """Moderation domain service."""

    def __init__(
        self,
        bot: Bot,
        chat_repository: IChatRepository,
        message_repository: IMessageRepository,
    ) -> None:
        self.bot = bot
        self.chat_repository = chat_repository
        self.message_repository = message_repository
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
            import datetime

            until_date = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=duration.seconds)

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
