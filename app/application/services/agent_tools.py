from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from pydantic import BaseModel

from app.core.logging import BotLogger
from app.domain.repositories import IChatRepository, IMessageRepository, IUserRepository


class ChatInfo(BaseModel):
    id: int
    title: str
    description: str | None = None
    member_count: int | None = None
    is_private: bool
    is_forum: bool
    welcome_enabled: bool
    welcome_text: str | None = None
    auto_delete_time: int | None = None
    captcha_enabled: bool
    auto_delete_join_leave: bool


class ChatUpdateRequest(BaseModel):
    description: str | None = None
    welcome_text: str | None = None
    welcome_enabled: bool | None = None
    auto_delete_time: int | None = None


class AgentTools:
    def __init__(
        self,
        chat_repository: IChatRepository,
        user_repository: IUserRepository,
        message_repository: IMessageRepository,
        bot: Bot,
        logger: BotLogger,
    ) -> None:
        self.chat_repository = chat_repository
        self.user_repository = user_repository
        self.message_repository = message_repository
        self.bot = bot
        self.logger = logger

    async def get_all_chats(self) -> list[ChatInfo]:
        """Get list of all managed chats with their current settings."""
        try:
            chats = await self.chat_repository.get_all()
            result = []

            for chat in chats:
                chat_info = ChatInfo(
                    id=chat.id,
                    title=chat.title or f"Chat {chat.id}",
                    description=getattr(chat, "description", None),
                    member_count=getattr(chat, "member_count", None),
                    is_private=not chat.is_forum,
                    is_forum=chat.is_forum,
                    welcome_enabled=chat.is_welcome_enabled,
                    welcome_text=chat.welcome_message,
                    auto_delete_time=chat.welcome_delete_time,
                    captcha_enabled=chat.is_captcha_enabled,
                    auto_delete_join_leave=chat.auto_delete_join_leave,
                )
                result.append(chat_info)

            self.logger.logger.info(f"Retrieved list of {len(result)} chats")
            return result

        except Exception as e:
            self.logger.logger.error(f"Error retrieving chat list: {e}", exc_info=True)
            return []

    async def get_chat_details(self, chat_id: int) -> ChatInfo | None:
        """
        Get detailed information about a specific chat.

        Returns complete chat settings including welcome message, member count, and moderation settings.
        Useful for reviewing current chat configuration before making changes.
        """
        try:
            chat = await self.chat_repository.get_by_id(chat_id)
            if not chat:
                self.logger.logger.warning(f"Chat {chat_id} not found")
                return None

            chat_info = ChatInfo(
                id=chat.id,
                title=chat.title or f"Chat {chat.id}",
                description=getattr(chat, "description", None),
                member_count=getattr(chat, "member_count", None),
                is_private=not chat.is_forum,
                is_forum=chat.is_forum,
                welcome_enabled=chat.is_welcome_enabled,
                welcome_text=chat.welcome_message,
                auto_delete_time=chat.welcome_delete_time,
                captcha_enabled=chat.is_captcha_enabled,
                auto_delete_join_leave=chat.auto_delete_join_leave,
            )

            self.logger.logger.info(f"Retrieved details for chat {chat_id}")
            return chat_info

        except Exception as e:
            self.logger.logger.error(f"Error retrieving chat {chat_id} details: {e}", exc_info=True)
            return None

    async def update_chat_settings(
        self,
        chat_id: int,
        title: str | None = None,
        welcome_text: str | None = None,
        welcome_enabled: bool | None = None,
        auto_delete_time: int | None = None,
        captcha_enabled: bool | None = None,
        auto_delete_join_leave: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update chat settings.

        Parameters:
        - chat_id: Telegram chat ID
        - title: New chat title
        - welcome_text: Welcome message for new members
        - welcome_enabled: Enable/disable welcome messages
        - auto_delete_time: Seconds before auto-deleting welcome, 0=disable
        - captcha_enabled: Enable/disable captcha for new members
        - auto_delete_join_leave: Auto-delete join/leave notifications

        Returns: {success: bool, updated_fields: list[str], error: str|None}
        """
        try:
            # Validate chat_id
            if chat_id <= 0:
                return {"success": False, "error": "Invalid chat_id: must be positive", "updated_fields": []}

            chat = await self.chat_repository.get_by_id(chat_id)
            if not chat:
                return {"success": False, "error": f"Chat {chat_id} not found", "updated_fields": []}

            updated_fields = []

            if title is not None and title.strip():
                chat.title = title.strip()
                updated_fields.append(f"title='{title.strip()}'")

            if welcome_text is not None:
                chat.welcome_message = welcome_text.strip() if welcome_text else None
                updated_fields.append(f"welcome_text='{welcome_text[:50]}...'")

            if welcome_enabled is not None:
                chat.is_welcome_enabled = welcome_enabled
                updated_fields.append(f"welcome_enabled={welcome_enabled}")

            if auto_delete_time is not None:
                if auto_delete_time < 0:
                    return {"success": False, "error": "auto_delete_time cannot be negative", "updated_fields": []}
                chat.welcome_delete_time = auto_delete_time
                updated_fields.append(f"auto_delete_time={auto_delete_time}")

            if captcha_enabled is not None:
                chat.is_captcha_enabled = captcha_enabled
                updated_fields.append(f"captcha_enabled={captcha_enabled}")

            if auto_delete_join_leave is not None:
                chat.auto_delete_join_leave = auto_delete_join_leave
                updated_fields.append(f"auto_delete_join_leave={auto_delete_join_leave}")

            if not updated_fields:
                return {"success": False, "error": "No fields to update", "updated_fields": []}

            await self.chat_repository.save(chat)

            self.logger.logger.info(f"Updated chat {chat_id} settings: {', '.join(updated_fields)}")
            return {"success": True, "updated_fields": updated_fields, "error": None}

        except Exception as e:
            self.logger.logger.error(f"Error updating chat {chat_id} settings: {e}", exc_info=True)
            return {"success": False, "error": str(e), "updated_fields": []}

    async def get_chat_statistics(self) -> dict[str, Any]:
        """
        Get general statistics across all managed chats.

        Returns statistics about:
        - Total number of chats
        - Forum vs regular chats
        - Chats with welcome messages enabled
        - Chats with captcha enabled
        - Total blocked users count
        """
        try:
            chats = await self.chat_repository.get_all()
            blocked_users = await self.user_repository.get_blocked_users()

            stats = {
                "success": True,
                "total_chats": len(chats),
                "forum_chats": len([c for c in chats if c.is_forum]),
                "regular_chats": len([c for c in chats if not c.is_forum]),
                "chats_with_welcome": len([c for c in chats if c.is_welcome_enabled]),
                "chats_with_captcha": len([c for c in chats if c.is_captcha_enabled]),
                "total_blocked_users": len(blocked_users),
                "error": None,
            }

            self.logger.logger.info("Retrieved general chat statistics")
            return stats

        except Exception as e:
            self.logger.logger.error(f"Error retrieving statistics: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def search_chats(self, query: str) -> list[ChatInfo]:
        """
        Search chats by title or description.

        Performs case-insensitive search across chat titles and descriptions.
        Useful for quickly finding specific chats when managing many communities.

        Parameters:
        - query: Search term (case-insensitive)

        Returns list of matching ChatInfo objects.
        """
        try:
            if not query or not query.strip():
                self.logger.logger.warning("Empty search query provided")
                return []

            all_chats = await self.get_all_chats()
            query_lower = query.strip().lower()

            filtered_chats = []
            for chat in all_chats:
                if query_lower in (chat.title or "").lower() or (
                    chat.description and query_lower in chat.description.lower()
                ):
                    filtered_chats.append(chat)

            self.logger.logger.info(f"Found {len(filtered_chats)} chats matching query '{query}'")
            return filtered_chats

        except Exception as e:
            self.logger.logger.error(f"Error searching chats: {e}", exc_info=True)
            return []

    async def get_recent_activity(
        self,
        chat_id: int | None = None,
        hours: int = 24,
    ) -> dict[str, Any]:
        """
        Get recent chat activity: messages, active users, spam attempts.

        Parameters:
        - chat_id: Specific chat ID or None for all chats
        - hours: Time window in hours (default 24)

        Returns: {
          success: bool,
          chat_id: int|None,
          time_window_hours: int,
          message_count: int,
          active_users: int,
          spam_messages: int,
          last_activity: datetime|None,
          error: str|None
        }
        """
        try:
            if chat_id and chat_id <= 0:
                return {"success": False, "error": "Invalid chat_id", "chat_id": chat_id}

            if chat_id:
                # Single chat stats
                message_count = await self.message_repository.get_message_count_24h(chat_id)
                active_users = await self.message_repository.get_active_users_24h(chat_id)
                last_activity = await self.message_repository.get_last_activity(chat_id)

                # Get spam messages in time window
                since = datetime.now() - timedelta(hours=hours)
                user_messages = await self.message_repository.get_user_messages(0)  # Get all
                spam_count = len(
                    [
                        m
                        for m in user_messages
                        if m.is_spam and m.chat_id == chat_id and m.timestamp and m.timestamp >= since
                    ]
                )

                self.logger.logger.info(f"Retrieved activity for chat {chat_id}")
                return {
                    "success": True,
                    "chat_id": chat_id,
                    "time_window_hours": hours,
                    "message_count": message_count,
                    "active_users": active_users,
                    "spam_messages": spam_count,
                    "last_activity": last_activity.isoformat() if last_activity else None,
                    "error": None,
                }
            # All chats aggregated
            chats = await self.chat_repository.get_all()
            total_messages = 0
            total_active_users = 0

            for chat in chats:
                total_messages += await self.message_repository.get_message_count_24h(chat.id)
                total_active_users += await self.message_repository.get_active_users_24h(chat.id)

            spam_messages = await self.message_repository.get_spam_messages()
            spam_count = len(spam_messages)

            self.logger.logger.info("Retrieved activity for all chats")
            return {
                "success": True,
                "chat_id": None,
                "time_window_hours": hours,
                "message_count": total_messages,
                "active_users": total_active_users,
                "spam_messages": spam_count,
                "error": None,
            }

        except Exception as e:
            self.logger.logger.error(f"Error retrieving activity: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_user_info(
        self,
        user_id: int,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Get detailed user info: profile, messages, block status, activity.

        Parameters:
        - user_id: Telegram user ID
        - chat_id: Optional chat context for chat-specific stats

        Returns: {
          success: bool,
          user_id: int,
          username: str|None,
          first_name: str|None,
          last_name: str|None,
          display_name: str,
          is_blocked: bool,
          is_verified: bool,
          total_messages: int,
          total_chats: int,
          spam_messages: int,
          created_at: datetime|None,
          error: str|None
        }
        """
        try:
            if user_id <= 0:
                return {"success": False, "error": "Invalid user_id"}

            user = await self.user_repository.get_by_id(user_id)
            if not user:
                return {"success": False, "error": f"User {user_id} not found"}

            # Get message statistics
            total_messages = await self.message_repository.count_user_messages(user_id)
            total_chats = await self.message_repository.count_user_chats(user_id)

            # Get spam count
            user_messages = await self.message_repository.get_user_messages(user_id, chat_id)
            spam_count = len([m for m in user_messages if m.is_spam])

            self.logger.logger.info(f"Retrieved info for user {user_id}")
            return {
                "success": True,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "display_name": user.display_name,
                "is_blocked": user.is_blocked,
                "is_verified": user.is_verified,
                "total_messages": total_messages,
                "total_chats": total_chats,
                "spam_messages": spam_count,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "error": None,
            }

        except Exception as e:
            self.logger.logger.error(f"Error retrieving user {user_id} info: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_blocked_users(
        self,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Get list of blocked users with details.

        Parameters:
        - limit: Max number of users to return (default 50)

        Returns: {
          success: bool,
          total_count: int,
          users: list[{user_id, username, display_name, blocked_at}],
          error: str|None
        }
        """
        try:
            if limit <= 0:
                return {"success": False, "error": "limit must be positive"}

            blocked_users = await self.user_repository.get_blocked_users()
            total_count = len(blocked_users)

            # Apply limit
            users_list = []
            for user in blocked_users[:limit]:
                users_list.append(
                    {
                        "user_id": user.id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "display_name": user.display_name,
                        "blocked_at": user.modified_at.isoformat() if user.modified_at else None,
                    }
                )

            self.logger.logger.info(f"Retrieved {len(users_list)} blocked users (total: {total_count})")
            return {
                "success": True,
                "total_count": total_count,
                "returned_count": len(users_list),
                "users": users_list,
                "error": None,
            }

        except Exception as e:
            self.logger.logger.error(f"Error retrieving blocked users: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_telegram_chat_info(self, chat_id: int) -> dict[str, Any]:
        """
        Get live chat info from Telegram API: description, member count, permissions.

        Parameters:
        - chat_id: Telegram chat ID (required)

        Returns: {
          success: bool,
          chat_id: int,
          title: str,
          type: str,
          description: str|None,
          member_count: int|None,
          username: str|None,
          permissions: dict|None,
          error: str|None
        }
        """
        try:
            if chat_id >= 0:
                return {"success": False, "error": "chat_id must be negative (group/channel ID)"}

            # Get chat info from Telegram
            chat = await self.bot.get_chat(chat_id)

            # Get member count
            member_count = None
            with suppress(TelegramBadRequest):
                member_count = await self.bot.get_chat_member_count(chat_id)

            self.logger.logger.info(f"Retrieved Telegram info for chat {chat_id}")
            return {
                "success": True,
                "chat_id": chat.id,
                "title": chat.title,
                "type": chat.type,
                "description": chat.description,
                "member_count": member_count,
                "username": chat.username,
                "permissions": {
                    "can_send_messages": chat.permissions.can_send_messages if chat.permissions else None,
                    "can_send_media": chat.permissions.can_send_other_messages if chat.permissions else None,
                    "can_add_web_page_previews": chat.permissions.can_add_web_page_previews
                    if chat.permissions
                    else None,
                }
                if chat.permissions
                else None,
                "error": None,
            }

        except TelegramBadRequest as e:
            self.logger.logger.warning(f"Telegram API error for chat {chat_id}: {e}")
            return {"success": False, "error": f"Telegram API error: {e}"}
        except Exception as e:
            self.logger.logger.error(f"Error retrieving Telegram info for chat {chat_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
