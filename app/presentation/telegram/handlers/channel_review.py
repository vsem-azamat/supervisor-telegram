"""Handlers for channel post review — inline button callbacks + discussion chat replies."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from aiogram import F, Router

from app.agent.channel.review import (
    CB_APPROVE,
    CB_LONGER,
    CB_REGEN,
    CB_REJECT,
    CB_SHORTER,
    CB_TRANSLATE,
    handle_approve,
    handle_edit_request,
    handle_regen,
    handle_reject,
)
from app.core.container import container
from app.core.logging import get_logger

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

logger = get_logger("handler.channel_review")

channel_review_router = Router(name="channel_review")


def _extract_post_id(callback_data: str, prefix: str) -> int | None:
    """Extract post ID from callback data."""
    try:
        return int(callback_data[len(prefix) :])
    except (ValueError, IndexError):
        return None


def _is_super_admin(user_id: int) -> bool:
    """Check if user is a super admin."""
    from app.core.config import settings

    return user_id in settings.admin.super_admins


def _get_config() -> tuple[Any, str]:
    """Get channel config and API key."""
    from app.agent.channel.config import ChannelAgentSettings
    from app.core.config import settings

    return ChannelAgentSettings(), settings.agent.openrouter_api_key


async def _get_post_channel_id(post_id: int, session_maker: Any) -> str | None:
    """Read channel_id from the ChannelPost DB record."""
    from sqlalchemy import select

    from app.infrastructure.db.models import ChannelPost

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost.channel_id).where(ChannelPost.id == post_id))
        row: str | None = result.scalar_one_or_none()
        return row


@channel_review_router.callback_query(F.data.startswith("chpost:"))
async def on_review_callback(callback: CallbackQuery) -> None:
    """Handle all channel post review button callbacks."""
    if not callback.data or not callback.message:
        return

    # Auth: only super admins can use review buttons
    if not callback.from_user or not _is_super_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    data = callback.data
    bot = callback.bot
    if not bot:
        return

    session_maker: Any = container.get("session_maker")
    if not session_maker:
        await callback.answer("Internal error: no DB session", show_alert=True)
        return

    channel_config, api_key = _get_config()
    chat_id = callback.message.chat.id

    if data.startswith(CB_APPROVE):
        post_id = _extract_post_id(data, CB_APPROVE)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        try:
            # Read channel_id from the DB post record (not from config)
            channel_id = await _get_post_channel_id(post_id, session_maker)
            if not channel_id:
                await callback.answer("Post not found or missing channel_id", show_alert=True)
                return
            result = await handle_approve(bot, post_id, channel_id, session_maker)
            await callback.answer(result, show_alert=True)

            if callback.message and "Published" in result:
                with contextlib.suppress(Exception):
                    await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logger.exception("approve_callback_error", post_id=post_id)
            await callback.answer("Internal error", show_alert=True)

    elif data.startswith(CB_REJECT):
        post_id = _extract_post_id(data, CB_REJECT)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        result = await handle_reject(post_id, session_maker)
        await callback.answer(result, show_alert=True)

        if callback.message:
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)

    elif data.startswith(CB_REGEN):
        post_id = _extract_post_id(data, CB_REGEN)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Regenerating...")
        try:
            from app.agent.channel.config import language_name

            language = language_name(channel_config.language)
            result = await handle_regen(
                bot,
                post_id,
                api_key,
                channel_config.generation_model,
                language,
                channel_config.review_chat_id,
                session_maker,
            )
            await bot.send_message(chat_id, result)
        except Exception:
            logger.exception("regen_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Regeneration failed.")

    elif data.startswith(CB_SHORTER):
        post_id = _extract_post_id(data, CB_SHORTER)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Making shorter...")
        try:
            result = await handle_edit_request(
                bot,
                post_id,
                "Make this post shorter and more concise. Keep the key info.",
                api_key,
                channel_config.generation_model,
                channel_config.review_chat_id,
                session_maker,
            )
            await bot.send_message(chat_id, result)
        except Exception:
            logger.exception("shorter_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Edit failed.")

    elif data.startswith(CB_LONGER):
        post_id = _extract_post_id(data, CB_LONGER)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Expanding...")
        try:
            result = await handle_edit_request(
                bot,
                post_id,
                "Expand this post with more details and context.",
                api_key,
                channel_config.generation_model,
                channel_config.review_chat_id,
                session_maker,
            )
            await bot.send_message(chat_id, result)
        except Exception:
            logger.exception("longer_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Edit failed.")

    elif data.startswith(CB_TRANSLATE):
        post_id = _extract_post_id(data, CB_TRANSLATE)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Translating...")
        try:
            target = "Czech" if channel_config.language == "ru" else "Russian"
            result = await handle_edit_request(
                bot,
                post_id,
                f"Translate this post to {target}. Keep the same Markdown formatting. No hashtags.",
                api_key,
                channel_config.generation_model,
                channel_config.review_chat_id,
                session_maker,
            )
            await bot.send_message(chat_id, result)
        except Exception:
            logger.exception("translate_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Translation failed.")


@channel_review_router.message(F.reply_to_message)
async def on_review_reply(message: Message) -> None:
    """Handle replies in the discussion chat — admin editing posts via conversation."""
    if not message.text or not message.reply_to_message:
        return

    # Auth: only super admins can edit via replies
    if not message.from_user or not _is_super_admin(message.from_user.id):
        return

    reply_msg = message.reply_to_message
    if not reply_msg.reply_markup:
        return

    # Find the post ID from the reply markup
    post_id: int | None = None
    if hasattr(reply_msg.reply_markup, "inline_keyboard"):
        for row in reply_msg.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith(CB_APPROVE):
                    post_id = _extract_post_id(btn.callback_data, CB_APPROVE)
                    break
            if post_id:
                break

    if not post_id:
        return

    bot = message.bot
    if not bot:
        return

    session_maker: Any = container.get("session_maker")
    if not session_maker:
        return

    channel_config, api_key = _get_config()

    result = await handle_edit_request(
        bot,
        post_id,
        message.text,
        api_key,
        channel_config.generation_model,
        channel_config.review_chat_id,
        session_maker,
    )

    await message.reply(result)
