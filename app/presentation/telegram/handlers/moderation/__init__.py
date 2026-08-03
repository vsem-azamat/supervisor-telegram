"""Moderation handlers — composed from per-concern submodules.

The composition is where the permission rule lives, because the rule is about
which group a command belongs to rather than what the command does. Mute, ban,
kick, pin, delete and the welcome text stop at the edge of one chat, so a
moderator of that chat may use them. The blacklist does not: `/banall` bans
somebody across all forty-five at once and can wipe what they wrote, teaching
the shared spam corpus on the way, so it stays with the super administrators.
"""

from aiogram import Router

from app.presentation.telegram.handlers.moderation.ban import ban_user, unban_user
from app.presentation.telegram.handlers.moderation.ban import router as _ban_router
from app.presentation.telegram.handlers.moderation.blacklist import (
    ban_everywhere,
    handle_blacklist_pagination,
    moved_to_banall,
    process_blacklist_cancel,
    process_blacklist_confirm,
    show_blacklist,
    unblock_user_callback,
)
from app.presentation.telegram.handlers.moderation.blacklist import router as _blacklist_router
from app.presentation.telegram.handlers.moderation.messages import (
    delete_message,
    kick_user,
    pin_message,
    purge_messages,
    unpin_message,
    user_info,
)
from app.presentation.telegram.handlers.moderation.messages import router as _messages_router
from app.presentation.telegram.handlers.moderation.mute import mute_user, unmute_user
from app.presentation.telegram.handlers.moderation.mute import router as _mute_router
from app.presentation.telegram.handlers.moderation.welcome import router as _welcome_router
from app.presentation.telegram.handlers.moderation.welcome import welcome_change
from app.presentation.telegram.middlewares.admin import AdminMiddleware, SuperAdminMiddleware

_CHAT_SCOPED = (_mute_router, _ban_router, _welcome_router, _messages_router)

for _router in _CHAT_SCOPED:
    _router.message.middleware(AdminMiddleware())
    _router.callback_query.middleware(AdminMiddleware())

# Reaches every chat, so it stays with the accounts in ADMIN_SUPER_ADMINS.
_blacklist_router.message.middleware(SuperAdminMiddleware())
_blacklist_router.callback_query.middleware(SuperAdminMiddleware())

moderation_router = Router(name="moderation")
moderation_router.include_router(_mute_router)
moderation_router.include_router(_ban_router)
moderation_router.include_router(_blacklist_router)
moderation_router.include_router(_welcome_router)
moderation_router.include_router(_messages_router)

__all__ = [
    "ban_user",
    "delete_message",
    "ban_everywhere",
    "handle_blacklist_pagination",
    "kick_user",
    "moved_to_banall",
    "moderation_router",
    "mute_user",
    "pin_message",
    "process_blacklist_cancel",
    "process_blacklist_confirm",
    "purge_messages",
    "show_blacklist",
    "unban_user",
    "unblock_user_callback",
    "unmute_user",
    "unpin_message",
    "user_info",
    "welcome_change",
]
