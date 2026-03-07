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

    from app.infrastructure.db.models import Channel

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


def _get_global_config() -> tuple[str, str]:
    """Get global settings: (generation_model, api_key)."""
    from app.core.config import settings

    return settings.channel.generation_model, settings.agent.openrouter_api_key


async def _get_channel_for_post(post_id: int, session_maker: Any) -> Channel | None:
    """Read the Channel DB record for a given post."""
    from sqlalchemy import select

    from app.infrastructure.db.models import Channel, ChannelPost

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost.channel_id).where(ChannelPost.id == post_id))
        channel_tid: str | None = result.scalar_one_or_none()
        if not channel_tid:
            return None
        ch_result = await session.execute(select(Channel).where(Channel.telegram_id == channel_tid))
        ch: Channel | None = ch_result.scalar_one_or_none()
        return ch


@channel_review_router.callback_query(F.data.startswith("chpost:"))
async def on_review_callback(callback: CallbackQuery) -> None:
    """Handle all channel post review button callbacks."""
    if not callback.data or not callback.message:
        return

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

    generation_model, api_key = _get_global_config()
    chat_id = callback.message.chat.id

    if data.startswith(CB_APPROVE):
        post_id = _extract_post_id(data, CB_APPROVE)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Post not found or channel not configured", show_alert=True)
                return
            result = await handle_approve(bot, post_id, channel.telegram_id, session_maker)
            await callback.answer(result, show_alert=True)

            if "Published" in result:
                from app.agent.channel.review_agent import clear_review_conversation

                clear_review_conversation(post_id)

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

        if "rejected" in result.lower():
            from app.agent.channel.review_agent import clear_review_conversation

            clear_review_conversation(post_id)

        if callback.message:
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)

    elif data.startswith(CB_REGEN):
        post_id = _extract_post_id(data, CB_REGEN)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Channel not found", show_alert=True)
                return
            await callback.answer("Regenerating...")
            language = _channel_language(channel)
            review_chat_id = channel.review_chat_id or chat_id
            result = await handle_regen(
                bot,
                post_id,
                api_key,
                generation_model,
                language,
                review_chat_id,
                session_maker,
                footer=channel.footer,
                channel_name=channel.name,
                channel_username=channel.username,
            )
            await bot.send_message(chat_id, result)
            from app.agent.channel.review_agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("regen_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Regeneration failed.")

    elif data.startswith(CB_SHORTER):
        post_id = _extract_post_id(data, CB_SHORTER)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Channel not found", show_alert=True)
                return
            await callback.answer("Making shorter...")
            review_chat_id = channel.review_chat_id or chat_id
            result = await handle_edit_request(
                bot,
                post_id,
                "Make this post shorter and more concise. Keep the key info.",
                api_key,
                generation_model,
                review_chat_id,
                session_maker,
                footer=channel.footer,
                channel_name=channel.name,
                channel_username=channel.username,
            )
            await bot.send_message(chat_id, result)
            from app.agent.channel.review_agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("shorter_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Edit failed.")

    elif data.startswith(CB_LONGER):
        post_id = _extract_post_id(data, CB_LONGER)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Channel not found", show_alert=True)
                return
            await callback.answer("Expanding...")
            review_chat_id = channel.review_chat_id or chat_id
            result = await handle_edit_request(
                bot,
                post_id,
                "Expand this post with more details and context.",
                api_key,
                generation_model,
                review_chat_id,
                session_maker,
                footer=channel.footer,
                channel_name=channel.name,
                channel_username=channel.username,
            )
            await bot.send_message(chat_id, result)
            from app.agent.channel.review_agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("longer_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Edit failed.")

    elif data.startswith(CB_TRANSLATE):
        post_id = _extract_post_id(data, CB_TRANSLATE)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Channel not found", show_alert=True)
                return
            await callback.answer("Translating...")
            language = _channel_language(channel)
            target = "Czech" if language == "Russian" else "Russian"
            review_chat_id = channel.review_chat_id or chat_id
            result = await handle_edit_request(
                bot,
                post_id,
                f"Translate this post to {target}. Keep the same Markdown formatting. No hashtags.",
                api_key,
                generation_model,
                review_chat_id,
                session_maker,
                footer=channel.footer,
                channel_name=channel.name,
                channel_username=channel.username,
            )
            await bot.send_message(chat_id, result)
            from app.agent.channel.review_agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("translate_callback_error", post_id=post_id)
            await bot.send_message(chat_id, "Translation failed.")

    elif data.startswith("chpost:noop:"):
        await callback.answer()


def _channel_language(channel: Channel | None) -> str:
    """Get the full language name for a channel, defaulting to Russian."""
    from app.agent.channel.config import language_name

    return language_name(channel.language if channel else "ru")


@channel_review_router.message(F.reply_to_message)
async def on_review_reply(message: Message) -> None:
    """Handle replies in the discussion chat — admin editing posts via conversation."""
    if not message.text or not message.reply_to_message:
        return

    if not message.from_user or not _is_super_admin(message.from_user.id):
        return

    reply_msg = message.reply_to_message
    if not reply_msg.reply_markup:
        return

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

    channel = await _get_channel_for_post(post_id, session_maker)
    if not channel:
        await message.reply("Channel not found.")
        return
    review_chat_id: int | str = channel.review_chat_id or message.chat.id

    try:
        from app.agent.channel.review_agent import ReviewAgentDeps, review_agent_turn

        deps = ReviewAgentDeps(
            session_maker=session_maker,
            bot=bot,
            post_id=post_id,
            channel_id=channel.telegram_id,
            channel_name=channel.name,
            channel_username=channel.username,
            footer=channel.footer,
            review_chat_id=review_chat_id,
        )
        result = await review_agent_turn(post_id, message.text, deps)
    except Exception:
        logger.exception("review_agent_reply_error", post_id=post_id)
        result = "Failed to process edit request."

    await message.reply(result)
