from aiogram import Router

from app.presentation.telegram.middlewares import (
    admin as admin_middlewares,
)
from app.presentation.telegram.middlewares import (
    chat_type as chat_type_middlewares,
)

from . import admin, agent_handler, channel_review, events, groups, moderation, service, start, webapp

router = Router()

moderation.moderation_router.message.middleware(admin_middlewares.AdminMiddleware())
moderation.moderation_router.callback_query.middleware(admin_middlewares.AdminMiddleware())
admin.admin_router.message.middleware(chat_type_middlewares.ChatTypeMiddleware(["group", "supergroup"]))
admin.admin_router.message.middleware(admin_middlewares.SuperAdminMiddleware())
groups.groups_router.message.middleware(chat_type_middlewares.ChatTypeMiddleware(["group", "supergroup"]))
service.router.message.middleware(admin_middlewares.AdminMiddleware())
agent_handler.agent_router.message.middleware(chat_type_middlewares.ChatTypeMiddleware(["group", "supergroup"]))

# Agent router first — /report and /spam go through LLM agent
router.include_router(agent_handler.agent_router)
router.include_router(moderation.moderation_router)
router.include_router(start.router)
router.include_router(admin.admin_router)
router.include_router(groups.groups_router)
router.include_router(service.router)
router.include_router(webapp.router)
router.include_router(channel_review.channel_review_router)
router.include_router(events.router)
