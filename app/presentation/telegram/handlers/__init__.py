from aiogram import Router

from app.presentation.telegram.middlewares import (
    admin as admin_middlewares,
)
from app.presentation.telegram.middlewares import (
    chat_type as chat_type_middlewares,
)

from . import admin, groups, moderation, service, start, webapp

router = Router()

moderation.moderation_router.message.middleware(admin_middlewares.AdminMiddleware())
admin.admin_router.message.middleware(chat_type_middlewares.ChatTypeMiddleware(["group", "supergroup"]))
admin.admin_router.message.middleware(admin_middlewares.SuperAdminMiddleware())
groups.groups_router.message.middleware(chat_type_middlewares.ChatTypeMiddleware(["group", "supergroup"]))
service.router.message.middleware(admin_middlewares.AdminMiddleware())

router.include_router(moderation.moderation_router)
router.include_router(start.router)
router.include_router(admin.admin_router)
router.include_router(groups.groups_router)
router.include_router(service.router)
router.include_router(webapp.router)
