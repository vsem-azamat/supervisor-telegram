"""Handlers for channel post review — inline button callbacks + discussion chat replies."""

from __future__ import annotations

import contextlib
import datetime
from datetime import UTC
from typing import TYPE_CHECKING, Any

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import Message as TgMessage

from app.channel.review import (
    build_review_keyboard,
    handle_approve,
    handle_delete,
    handle_edit_request,
    handle_regen,
    handle_reject,
)
from app.core.container import container
from app.core.logging import get_logger
from app.presentation.telegram.utils.callback_data import PublishNow, ReviewAction, SchedulePick, SchedulePreset

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

    from app.db.models import Channel

logger = get_logger("handler.channel_review")

channel_review_router = Router(name="channel_review")


# ── Helpers ──


def _is_super_admin(user_id: int) -> bool:
    """Check if user is a super admin."""
    from app.core.config import settings

    return user_id in settings.admin.super_admins


def _get_global_config() -> tuple[str, str]:
    """Get global settings: (generation_model, api_key)."""
    from app.core.config import settings

    return settings.channel.generation_model, settings.openrouter.api_key


async def _get_channel_for_post(post_id: int, session_maker: Any) -> Channel | None:
    """Read the Channel DB record for a given post."""
    from sqlalchemy import select

    from app.db.models import Channel, ChannelPost

    async with session_maker() as session:
        result = await session.execute(select(ChannelPost.channel_id).where(ChannelPost.id == post_id))
        channel_tid: int | None = result.scalar_one_or_none()
        if not channel_tid:
            return None
        ch_result = await session.execute(select(Channel).where(Channel.telegram_id == channel_tid))
        ch: Channel | None = ch_result.scalar_one_or_none()
        return ch


def _channel_language(channel: Channel | None) -> str:
    """Get the full language name for a channel, defaulting to Russian."""
    from app.channel.config import language_name

    return language_name(channel.language if channel else "ru")


def _get_session_maker() -> Any:
    return container.get_session_maker()


# ── Callback handlers using CallbackData factories ──


@channel_review_router.callback_query(ReviewAction.filter())
async def on_review_action(callback: CallbackQuery, callback_data: ReviewAction) -> None:
    """Handle all single-action review callbacks (approve, reject, delete, etc.)."""
    if not isinstance(callback.message, TgMessage):
        return
    if not callback.from_user or not _is_super_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    bot = callback.bot
    if not bot:
        return

    session_maker = _get_session_maker()
    if not session_maker:
        await callback.answer("Internal error: no DB session", show_alert=True)
        return

    action = callback_data.action
    post_id = callback_data.post_id
    generation_model, api_key = _get_global_config()
    chat_id = callback.message.chat.id

    if action == "approve":
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Post not found or channel not configured", show_alert=True)
                return
            publish_bot = container.try_get_bot() or bot
            result = await handle_approve(publish_bot, post_id, channel.telegram_id, session_maker)
            await callback.answer(result, show_alert=True)

            if "Published" in result:
                from app.channel.review.agent import clear_reply_chain_from_db, clear_review_conversation

                clear_review_conversation(post_id)
                await clear_reply_chain_from_db(session_maker, post_id)
                with contextlib.suppress(Exception):
                    await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            logger.exception("approve_callback_error", post_id=post_id)
            await callback.answer("Internal error", show_alert=True)

    elif action == "reject":
        result = await handle_reject(post_id, session_maker)
        await callback.answer(result, show_alert=True)

        if "rejected" in result.lower():
            from app.channel.review.agent import clear_reply_chain_from_db, clear_review_conversation

            clear_review_conversation(post_id)
            await clear_reply_chain_from_db(session_maker, post_id)
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=callback.message.message_id)

    elif action == "delete":
        try:
            review_message_id = callback.message.message_id
            result = await handle_delete(bot, post_id, chat_id, review_message_id, session_maker)
            if "skipped" not in result.lower():
                await callback.answer(result, show_alert=True)
            else:
                from app.channel.review.agent import clear_reply_chain_from_db, clear_review_conversation

                clear_review_conversation(post_id)
                await clear_reply_chain_from_db(session_maker, post_id)
                await callback.answer("Post skipped")
        except Exception:
            logger.exception("delete_callback_error", post_id=post_id)
            await callback.answer("Delete failed", show_alert=True)

    elif action == "schedule":
        # Show time preset picker
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        presets = [
            ("5m", 5),
            ("15m", 15),
            ("30m", 30),
            ("1h", 60),
            ("2h", 120),
            ("3h", 180),
            ("6h", 360),
            ("12h", 720),
            ("24h", 1440),
        ]
        schedule_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"⏱ {label}",
                        callback_data=SchedulePreset(post_id=post_id, minutes=mins).pack(),
                    )
                    for label, mins in presets[:3]
                ],
                [
                    InlineKeyboardButton(
                        text=f"⏱ {label}",
                        callback_data=SchedulePreset(post_id=post_id, minutes=mins).pack(),
                    )
                    for label, mins in presets[3:6]
                ],
                [
                    InlineKeyboardButton(
                        text=f"⏱ {label}",
                        callback_data=SchedulePreset(post_id=post_id, minutes=mins).pack(),
                    )
                    for label, mins in presets[6:]
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Back",
                        callback_data=ReviewAction(action="back", post_id=post_id).pack(),
                    ),
                ],
            ]
        )
        await callback.message.edit_reply_markup(reply_markup=schedule_kb)
        await callback.answer()

    elif action == "regen":
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
            logger.info("regen_result", post_id=post_id, result=result)
            from app.channel.review.agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("regen_callback_error", post_id=post_id)
            await callback.answer("Regeneration failed.", show_alert=True)

    elif action == "shorter":
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
            logger.info("shorter_result", post_id=post_id, result=result)
            from app.channel.review.agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("shorter_callback_error", post_id=post_id)
            await callback.answer("Edit failed.", show_alert=True)

    elif action == "longer":
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
            logger.info("longer_result", post_id=post_id, result=result)
            from app.channel.review.agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("longer_callback_error", post_id=post_id)
            await callback.answer("Edit failed.", show_alert=True)

    elif action == "translate":
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
            logger.info("translate_result", post_id=post_id, result=result)
            from app.channel.review.agent import clear_review_conversation

            clear_review_conversation(post_id)
        except Exception:
            logger.exception("translate_callback_error", post_id=post_id)
            await callback.answer("Translation failed.", show_alert=True)

    elif action == "back":
        try:
            channel = await _get_channel_for_post(post_id, session_maker)
            if not channel:
                await callback.answer("Channel not found", show_alert=True)
                return
            from sqlalchemy import select

            from app.channel.review import extract_source_btn_data
            from app.db.models import ChannelPost

            async with session_maker() as session:
                r = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
                post = r.scalar_one_or_none()

            source_btn_data = extract_source_btn_data(post) if post else []
            keyboard = build_review_keyboard(
                post_id,
                source_items=source_btn_data,
                channel_name=channel.name,
                channel_username=channel.username,
            )
            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer()
        except Exception:
            logger.exception("back_callback_error", post_id=post_id)
            await callback.answer("Failed to restore keyboard", show_alert=True)

    elif action == "noop":
        await callback.answer()


@channel_review_router.callback_query(SchedulePick.filter())
async def on_schedule_pick(callback: CallbackQuery, callback_data: SchedulePick) -> None:
    """Handle schedule time slot selection."""
    if not isinstance(callback.message, TgMessage):
        return
    if not callback.from_user or not _is_super_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    bot = callback.bot
    if not bot:
        return

    session_maker = _get_session_maker()
    if not session_maker:
        await callback.answer("Internal error: no DB session", show_alert=True)
        return

    post_id = callback_data.post_id
    from datetime import datetime

    schedule_time = datetime.fromtimestamp(callback_data.ts, tz=UTC).replace(tzinfo=None)

    try:
        channel = await _get_channel_for_post(post_id, session_maker)
        if not channel:
            await callback.answer("Channel not found", show_alert=True)
            return

        tc = container.get_telethon_client()
        if not tc or not tc.is_available:
            await callback.answer("Scheduling unavailable (Telethon not connected)", show_alert=True)
            return

        from app.channel.schedule_manager import schedule_post

        result = await schedule_post(tc, session_maker, post_id, channel, schedule_time)
        await callback.answer(result, show_alert=True)

        if "Scheduled" in result:
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("schedule_pick_error", post_id=post_id)
        await callback.answer("Scheduling failed", show_alert=True)


@channel_review_router.callback_query(PublishNow.filter())
async def on_publish_now(callback: CallbackQuery, callback_data: PublishNow) -> None:
    """Handle 'Publish now' from the schedule picker."""
    if not isinstance(callback.message, TgMessage):
        return
    if not callback.from_user or not _is_super_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    bot = callback.bot
    if not bot:
        return

    session_maker = _get_session_maker()
    if not session_maker:
        await callback.answer("Internal error: no DB session", show_alert=True)
        return

    post_id = callback_data.post_id

    try:
        channel = await _get_channel_for_post(post_id, session_maker)
        if not channel:
            await callback.answer("Channel not found", show_alert=True)
            return

        # If post is currently scheduled, cancel the schedule first
        from sqlalchemy import select

        from app.core.enums import PostStatus
        from app.db.models import ChannelPost

        async with session_maker() as session:
            r = await session.execute(select(ChannelPost).where(ChannelPost.id == post_id))
            post = r.scalar_one_or_none()

        if post and post.status == PostStatus.SCHEDULED:
            tc = container.get_telethon_client()
            if tc and tc.is_available:
                from app.channel.schedule_manager import cancel_scheduled_post

                await cancel_scheduled_post(tc, session_maker, post_id, channel)

        # Use moderator bot for publishing (callback.bot may be the assistant bot)
        publish_bot = container.try_get_bot() or bot
        result = await handle_approve(publish_bot, post_id, channel.telegram_id, session_maker)
        await callback.answer(result, show_alert=True)

        if "Published" in result:
            from app.channel.review.agent import clear_review_conversation

            clear_review_conversation(post_id)
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("publish_now_error", post_id=post_id)
        await callback.answer("Publish failed", show_alert=True)


@channel_review_router.callback_query(SchedulePreset.filter())
async def on_schedule_preset(callback: CallbackQuery, callback_data: SchedulePreset) -> None:
    """Handle schedule time preset (e.g. +5m, +1h, +3h)."""
    if not isinstance(callback.message, TgMessage):
        return
    if not callback.from_user or not _is_super_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    bot = callback.bot
    if not bot:
        return

    session_maker = _get_session_maker()
    if not session_maker:
        await callback.answer("Internal error: no DB session", show_alert=True)
        return

    post_id = callback_data.post_id
    minutes = callback_data.minutes

    try:
        channel = await _get_channel_for_post(post_id, session_maker)
        if not channel:
            await callback.answer("Channel not found", show_alert=True)
            return

        tc = container.get_telethon_client()
        if not tc or not tc.is_available:
            await callback.answer("Scheduling unavailable (Telethon not connected)", show_alert=True)
            return

        from app.channel.schedule_manager import schedule_post
        from app.core.time import utc_now

        schedule_time = utc_now() + datetime.timedelta(minutes=minutes)
        result = await schedule_post(tc, session_maker, post_id, channel, schedule_time)
        await callback.answer(result, show_alert=True)

        if "Scheduled" in result:
            from app.channel.review.agent import clear_review_conversation

            clear_review_conversation(post_id)
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception("schedule_preset_error", post_id=post_id, minutes=minutes)
        await callback.answer("Scheduling failed", show_alert=True)


# ── Reply handler for review agent conversation ──


def _resolve_post_id_from_reply(reply_msg: Message) -> int | None:
    """Resolve post_id from a reply target — checks inline keyboard first, then message mapping."""
    # 1. Try inline keyboard (reply to the original review post)
    if reply_msg.reply_markup and hasattr(reply_msg.reply_markup, "inline_keyboard"):
        for row in reply_msg.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data:
                    try:
                        rv = ReviewAction.unpack(btn.callback_data)
                        return rv.post_id
                    except (ValueError, KeyError):
                        pass

    # 2. Try message_id mapping (reply to an agent response in the conversation chain)
    from app.channel.review.agent import resolve_post_id

    return resolve_post_id(reply_msg.message_id)


class _IsReviewReply(Filter):
    """Only match replies that resolve to a review post_id.

    Returns False for non-review replies so they propagate to the next router
    (e.g. the assistant bot's generic F.text handler).

    Resolution order:
    1. Inline keyboard on replied-to message (direct reply to review post)
    2. In-memory message_to_post mapping (reply to agent response, same session)
    3. DB fallback via reply_chain_message_ids (survives bot restarts)
    """

    async def __call__(self, message: Message) -> bool | dict[str, int]:
        if not message.text or not message.reply_to_message:
            return False
        if not message.from_user or not _is_super_admin(message.from_user.id):
            return False

        # 1 & 2: sync resolution (keyboard + in-memory)
        post_id = _resolve_post_id_from_reply(message.reply_to_message)

        # 3: async DB fallback (survives restart)
        if not post_id:
            session_maker = _get_session_maker()
            if session_maker:
                from app.channel.review.agent import register_message, resolve_post_id_from_db

                post_id = await resolve_post_id_from_db(
                    session_maker, message.reply_to_message.message_id, message.chat.id
                )
                if post_id:
                    # Cache in memory for subsequent replies in this session
                    register_message(message.reply_to_message.message_id, post_id)

        if not post_id:
            return False
        return {"post_id": post_id}


@channel_review_router.message(_IsReviewReply())
async def on_review_reply(message: Message, post_id: int) -> None:
    """Handle replies in the discussion chat — admin editing posts via conversation.

    Supports reply chains: the user can reply to the original review post OR to any
    agent response in the conversation. The post_id is resolved by the _IsReviewReply filter.
    """

    bot = message.bot
    if not bot:
        return

    session_maker = _get_session_maker()
    if not session_maker:
        return

    channel = await _get_channel_for_post(post_id, session_maker)
    if not channel:
        await message.reply("Channel not found.")
        return
    review_chat_id: int | str = channel.review_chat_id or message.chat.id

    # Register the user's message in the chain so future replies to it also work
    from app.channel.review.agent import (
        ReviewAgentDeps,
        persist_message_to_db,
        register_message,
        review_agent_turn,
    )

    register_message(message.message_id, post_id)
    await persist_message_to_db(session_maker, post_id, message.message_id)

    try:
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
        result = await review_agent_turn(post_id, message.text or "", deps)
    except Exception:
        logger.exception("review_agent_reply_error", post_id=post_id)
        result = "Failed to process edit request."

    from app.core.markdown import md_to_entities

    plain, entities = md_to_entities(result)
    reply = await message.reply(plain, entities=entities, parse_mode=None)

    # Register the agent's response so the user can reply to it and continue the chain
    register_message(reply.message_id, post_id)
    await persist_message_to_db(session_maker, post_id, reply.message_id)
