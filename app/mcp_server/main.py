"""MCP Server for Moderator Bot."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bot_factory import create_bot
from app.core.container import get_container, setup_container
from app.domain.repositories import IChatRepository, IUserRepository
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
    title: str | None = None,
    welcome_message: str | None = None,
    welcome_enabled: bool | None = None,
) -> dict[str, Any]:
    """
    Update chat settings: welcome message and title.
    """
    async with get_db_session() as session:
        chat_repo = get_chat_repo(session)
        chat = await chat_repo.get_by_id(chat_id)
        if not chat:
            return {"success": False, "error": "Chat not found"}

        if title is not None:
            chat.title = title
        if welcome_message is not None:
            chat.welcome_message = welcome_message
        if welcome_enabled is not None:
            chat.is_welcome_enabled = welcome_enabled

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
        }


if __name__ == "__main__":
    mcp.run()
