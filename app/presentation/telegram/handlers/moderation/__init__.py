"""Moderation handlers — composed from per-concern submodules."""

from aiogram import Router

from app.presentation.telegram.handlers.moderation.ban import ban_user, unban_user
from app.presentation.telegram.handlers.moderation.ban import router as _ban_router
from app.presentation.telegram.handlers.moderation.blacklist import (
    full_ban,
    handle_blacklist_pagination,
    label_spam,
    process_blacklist_cancel,
    process_blacklist_confirm,
    show_blacklist,
    unblock_user_callback,
)
from app.presentation.telegram.handlers.moderation.blacklist import router as _blacklist_router
from app.presentation.telegram.handlers.moderation.mute import mute_user, unmute_user
from app.presentation.telegram.handlers.moderation.mute import router as _mute_router
from app.presentation.telegram.handlers.moderation.welcome import router as _welcome_router
from app.presentation.telegram.handlers.moderation.welcome import welcome_change

moderation_router = Router(name="moderation")
moderation_router.include_router(_mute_router)
moderation_router.include_router(_ban_router)
moderation_router.include_router(_blacklist_router)
moderation_router.include_router(_welcome_router)

__all__ = [
    "ban_user",
    "full_ban",
    "handle_blacklist_pagination",
    "label_spam",
    "moderation_router",
    "mute_user",
    "process_blacklist_cancel",
    "process_blacklist_confirm",
    "show_blacklist",
    "unban_user",
    "unblock_user_callback",
    "unmute_user",
    "welcome_change",
]
