"""MCP Server for Moderator Bot."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bot_factory import create_bot
from app.core.container import get_container, setup_container
from app.domain.repositories import IChatRepository, IMessageRepository, IUserRepository
from app.infrastructure.db.session import create_session_maker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize application components
session_maker = create_session_maker()
bot = create_bot()
setup_container(session_maker, bot)

container = get_container()

# Create FastMCP server
mcp = FastMCP("Moderator")


# --- DI Helpers ---


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide a database session from the DI container."""
    async with container.get_session() as session:
        yield session


def get_chat_repo(session: AsyncSession) -> IChatRepository:
    """Resolve chat repository from DI container."""
    return container.get_chat_repository(session)


def get_user_repo(session: AsyncSession) -> IUserRepository:
    """Resolve user repository from DI container."""
    return container.get_user_repository(session)


def get_message_repo(session: AsyncSession) -> IMessageRepository:
    """Resolve message repository from DI container."""
    return container.get_message_repository(session)


# --- MCP Tools ---


@mcp.tool()
async def get_all_chats() -> list[dict[str, Any]]:
    """Get list of all managed chats with their current settings."""
    async with get_db_session() as session:
        chat_repo = get_chat_repo(session)
        chats = await chat_repo.get_all()
        return [
            {
                "id": c.id,
                "title": c.title,
                "welcome_message": c.welcome_message,
                "is_welcome_enabled": c.is_welcome_enabled,
                "is_captcha_enabled": c.is_captcha_enabled,
            }
            for c in chats
        ]


@mcp.tool()
async def get_chat_details(chat_id: int) -> dict[str, Any] | None:
    """
    Get detailed information about a specific chat.
    Returns complete chat settings including welcome message and moderation settings.
    """
    async with get_db_session() as session:
        chat_repo = get_chat_repo(session)
        chat = await chat_repo.get_by_id(chat_id)
        if not chat:
            return None
        return {
            "id": chat.id,
            "title": chat.title,
            "welcome_message": chat.welcome_message,
            "welcome_delete_time": chat.welcome_delete_time,
            "is_welcome_enabled": chat.is_welcome_enabled,
            "is_captcha_enabled": chat.is_captcha_enabled,
            "auto_delete_join_leave": chat.auto_delete_join_leave,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
            "updated_at": chat.modified_at.isoformat() if chat.modified_at else None,
        }


@mcp.tool()
async def update_chat_settings(
    chat_id: int,
    welcome_message: str | None = None,
    welcome_enabled: bool | None = None,
    welcome_delete_time: int | None = None,
    captcha_enabled: bool | None = None,
    auto_delete_join_leave: bool | None = None,
) -> dict[str, Any]:
    """
    Update chat settings: welcome message and title.
    """
    async with get_db_session() as session:
        chat_repo = get_chat_repo(session)
        chat = await chat_repo.get_by_id(chat_id)
        if not chat:
            return {"success": False, "error": "Chat not found"}

        if welcome_message is not None:
            chat.welcome_message = welcome_message
        if welcome_enabled is not None:
            chat.is_welcome_enabled = welcome_enabled
        if welcome_delete_time is not None:
            try:
                chat.set_welcome_delete_time(welcome_delete_time)
            except ValueError as e:
                return {"success": False, "error": str(e)}
        if captcha_enabled is not None:
            if captcha_enabled:
                chat.enable_captcha()
            else:
                chat.disable_captcha()
        if auto_delete_join_leave is not None:
            if auto_delete_join_leave:
                chat.enable_auto_delete_join_leave()
            else:
                chat.disable_auto_delete_join_leave()

        await chat_repo.save(chat)
        await session.commit()
        return {"success": True, "chat_id": chat_id}


@mcp.tool()
async def get_chat_statistics() -> dict[str, Any]:
    """
    Get general statistics across all managed chats.
    """
    async with get_db_session() as session:
        chat_repo = get_chat_repo(session)
        chats = await chat_repo.get_all()
        return {
            "total_chats": len(chats),
            "active_chats": len([c for c in chats if c.is_welcome_enabled or c.is_captcha_enabled]),
        }


@mcp.tool()
async def get_chat_activity_report(chat_id: int) -> dict[str, Any]:
    """
    Get activity report for a specific chat (last 24 hours).
    Includes message count, active users, and last activity timestamp.
    """
    async with get_db_session() as session:
        message_repo = get_message_repo(session)

        # Check if chat exists first (optional but good practice, though repos handle it gracefully usually)
        # Using chat repo for existence check
        chat_repo = get_chat_repo(session)
        if not await chat_repo.exists(chat_id):
            return {"error": "Chat not found"}

        message_count = await message_repo.get_message_count_24h(chat_id)
        active_users = await message_repo.get_active_users_24h(chat_id)
        last_activity = await message_repo.get_last_activity(chat_id)

        return {
            "chat_id": chat_id,
            "messages_24h": message_count,
            "active_users_24h": active_users,
            "last_activity": last_activity.isoformat() if last_activity else None,
        }


@mcp.tool()
async def get_user_info(user_id: int) -> dict[str, Any] | None:
    """
    Get user information by ID.
    """
    async with get_db_session() as session:
        user_repo = get_user_repo(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_blocked": user.is_blocked,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "stats": {
                "total_messages": await get_message_repo(session).count_user_messages(user_id),
                "chats_participated": await get_message_repo(session).count_user_chats(user_id),
            },
        }


if __name__ == "__main__":
    mcp.run()
