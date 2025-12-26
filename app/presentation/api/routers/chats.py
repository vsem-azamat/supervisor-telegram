"""Chat management API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.telegram_stats import TelegramStatsService
from app.core.bot_factory import get_bot
from app.infrastructure.db.repositories.admin import AdminRepository
from app.infrastructure.db.repositories.chat import ChatRepository
from app.infrastructure.db.repositories.message import MessageRepository
from app.infrastructure.db.session import get_db_session
from app.presentation.api.auth import get_current_admin_user
from app.presentation.api.schemas.chat import BulkUpdateRequest, ChatResponse, ChatStatsResponse, ChatUpdateRequest

router = APIRouter()


async def get_chat_repository(db: AsyncSession = Depends(get_db_session)) -> ChatRepository:
    """Get chat repository dependency."""
    return ChatRepository(db)


async def get_message_repository(db: AsyncSession = Depends(get_db_session)) -> MessageRepository:
    """Get message repository dependency."""
    return MessageRepository(db)


async def get_admin_repository(db: AsyncSession = Depends(get_db_session)) -> AdminRepository:
    """Get admin repository dependency."""
    return AdminRepository(db)


def get_telegram_stats_service() -> TelegramStatsService:
    """Get Telegram stats service dependency."""
    bot = get_bot()
    return TelegramStatsService(bot)


@router.get("", response_model=list[ChatResponse])
async def get_all_chats(
    chat_repo: ChatRepository = Depends(get_chat_repository),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> list[ChatResponse]:
    """Get all chats with their configurations."""
    try:
        chats = await chat_repo.get_all()
        return [ChatResponse.from_entity(chat) for chat in chats]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}") from None


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: int,
    chat_repo: ChatRepository = Depends(get_chat_repository),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> ChatResponse:
    """Get specific chat by ID."""
    try:
        chat = await chat_repo.get_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        return ChatResponse.from_entity(chat)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat: {str(e)}") from None


@router.put("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: int,
    update_data: ChatUpdateRequest,
    chat_repo: ChatRepository = Depends(get_chat_repository),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> ChatResponse:
    """Update chat configuration."""
    try:
        chat = await chat_repo.get_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Update chat properties
        if update_data.welcome_message is not None:
            chat.welcome_message = update_data.welcome_message
        if update_data.welcome_delete_time is not None:
            chat.set_welcome_delete_time(update_data.welcome_delete_time)
        if update_data.is_welcome_enabled is not None:
            if update_data.is_welcome_enabled:
                chat.enable_welcome()
            else:
                chat.disable_welcome()
        if update_data.is_captcha_enabled is not None:
            if update_data.is_captcha_enabled:
                chat.enable_captcha()
            else:
                chat.disable_captcha()

        updated_chat = await chat_repo.save(chat)
        return ChatResponse.from_entity(updated_chat)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chat: {str(e)}") from None


@router.get("/{chat_id}/stats", response_model=ChatStatsResponse)
async def get_chat_stats(
    chat_id: int,
    chat_repo: ChatRepository = Depends(get_chat_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    telegram_stats: TelegramStatsService = Depends(get_telegram_stats_service),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> ChatStatsResponse:
    """Get chat statistics and analytics."""
    try:
        chat = await chat_repo.get_by_id(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Get real statistics
        member_count = await telegram_stats.get_chat_member_count(chat_id)
        message_count_24h = await message_repo.get_message_count_24h(chat_id)
        active_users_24h = await message_repo.get_active_users_24h(chat_id)
        last_activity = await message_repo.get_last_activity(chat_id)

        return ChatStatsResponse(
            chat_id=chat_id,
            member_count=member_count,
            message_count_24h=message_count_24h,
            active_users_24h=active_users_24h,
            moderation_actions_24h=0,  # TODO: Add moderation log tracking
            last_activity=last_activity,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat stats: {str(e)}") from None


@router.post("/bulk-update", response_model=list[ChatResponse])
async def bulk_update_chats(
    request: BulkUpdateRequest,
    chat_repo: ChatRepository = Depends(get_chat_repository),
    _current_user: dict[str, Any] = Depends(get_current_admin_user),
) -> list[ChatResponse]:
    """Perform bulk operations on multiple chats."""
    try:
        updated_chats = []

        for chat_id in request.chat_ids:
            chat = await chat_repo.get_by_id(chat_id)
            if not chat:
                continue  # Skip non-existent chats

            # Apply updates
            if request.update_data.welcome_message is not None:
                chat.welcome_message = request.update_data.welcome_message
            if request.update_data.welcome_delete_time is not None:
                chat.set_welcome_delete_time(request.update_data.welcome_delete_time)
            if request.update_data.is_welcome_enabled is not None:
                if request.update_data.is_welcome_enabled:
                    chat.enable_welcome()
                else:
                    chat.disable_welcome()
            if request.update_data.is_captcha_enabled is not None:
                if request.update_data.is_captcha_enabled:
                    chat.enable_captcha()
                else:
                    chat.disable_captcha()

            updated_chat = await chat_repo.save(chat)
            updated_chats.append(ChatResponse.from_entity(updated_chat))

        return updated_chats
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bulk update chats: {str(e)}") from None
