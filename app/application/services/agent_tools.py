from typing import Any

from pydantic import BaseModel

from app.core.logging import BotLogger
from app.domain.repositories import IChatRepository, IUserRepository


class ChatInfo(BaseModel):
    id: int
    title: str
    description: str | None = None
    member_count: int | None = None
    is_private: bool
    welcome_enabled: bool
    welcome_text: str | None = None
    auto_delete_time: int | None = None


class ChatUpdateRequest(BaseModel):
    description: str | None = None
    welcome_text: str | None = None
    welcome_enabled: bool | None = None
    auto_delete_time: int | None = None


class AgentTools:
    def __init__(self, chat_repository: IChatRepository, user_repository: IUserRepository, logger: BotLogger) -> None:
        self.chat_repository = chat_repository
        self.user_repository = user_repository
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
                    is_private=not chat.is_forum,  # invert is_forum to get is_private
                    welcome_enabled=chat.is_welcome_enabled,
                    welcome_text=chat.welcome_message,
                    auto_delete_time=chat.welcome_delete_time,
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
                welcome_enabled=chat.is_welcome_enabled,
                welcome_text=chat.welcome_message,
                auto_delete_time=chat.welcome_delete_time,
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
    ) -> dict[str, Any]:
        """
        Update chat settings (welcome message, auto-delete timer, etc.).

        Parameters:
        - chat_id: Telegram chat ID
        - title: New chat title (optional)
        - welcome_text: Welcome message for new members (optional)
        - welcome_enabled: Enable/disable welcome messages (optional)
        - auto_delete_time: Seconds before auto-deleting welcome message, 0 to disable (optional)

        Returns dict with:
        - success: bool
        - updated_fields: list of changed fields
        - error: error message if failed
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
