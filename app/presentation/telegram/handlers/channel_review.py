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


def _get_config() -> tuple[Any, str]:
    """Get channel config and API key."""
    from app.agent.channel.config import ChannelAgentSettings
    from app.core.config import settings

    return ChannelAgentSettings(), settings.agent.openrouter_api_key


@channel_review_router.callback_query(F.data.startswith("chpost:"))
async def on_review_callback(callback: CallbackQuery) -> None:
    """Handle all channel post review button callbacks."""
    if not callback.data or not callback.message:
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
        result = await handle_approve(bot, post_id, channel_config.channel_id, session_maker)
        await callback.answer(result, show_alert=True)

        if callback.message and "Published" in result:
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)

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
        language = {"ru": "Russian", "cs": "Czech", "en": "English"}.get(channel_config.language, "Russian")
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

    elif data.startswith(CB_SHORTER):
        post_id = _extract_post_id(data, CB_SHORTER)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Making shorter...")
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

    elif data.startswith(CB_LONGER):
        post_id = _extract_post_id(data, CB_LONGER)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Expanding...")
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

    elif data.startswith(CB_TRANSLATE):
        post_id = _extract_post_id(data, CB_TRANSLATE)
        if not post_id:
            await callback.answer("Invalid post ID")
            return
        await callback.answer("Translating...")
        target = "Czech" if channel_config.language == "ru" else "Russian"
        result = await handle_edit_request(
            bot,
            post_id,
            f"Translate this post to {target}. Keep the same HTML formatting and hashtags.",
            api_key,
            channel_config.generation_model,
            channel_config.review_chat_id,
            session_maker,
        )
        await bot.send_message(chat_id, result)


@channel_review_router.message(F.reply_to_message)
async def on_review_reply(message: Message) -> None:
    """Handle replies in the discussion chat — admin editing posts via conversation."""
    if not message.text or not message.reply_to_message:
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
