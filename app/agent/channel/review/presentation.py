"""Review flow — Telegram presentation layer.

Sends drafts to the review channel with inline buttons, handles callbacks.
Business logic and DB operations are delegated to service.py.
"""

from __future__ import annotations

import calendar
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, URLInputFile

from app.agent.channel.review.service import (
    CB_APPROVE,
    CB_BACK,
    CB_DELETE,
    CB_LONGER,
    CB_PUBLISH_NOW,
    CB_REGEN,
    CB_REJECT,
    CB_SCHEDULE,
    CB_SCHEDULE_PICK,
    CB_SHORTER,
    CB_TRANSLATE,
    approve_post,
    create_review_post,
    delete_post,
    edit_post_text,
    extract_source_btn_data,
    regen_post_text,
    reject_post,
)
from app.core.logging import get_logger
from app.core.markdown import md_to_entities

if TYPE_CHECKING:
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.generator import GeneratedPost
    from app.agent.channel.sources import ContentItem

logger = get_logger("channel.review")

# Re-export callback constants so existing importers don't break
__all__ = [
    "CB_APPROVE",
    "CB_BACK",
    "CB_DELETE",
    "CB_LONGER",
    "CB_PUBLISH_NOW",
    "CB_REGEN",
    "CB_REJECT",
    "CB_SCHEDULE",
    "CB_SCHEDULE_PICK",
    "CB_SHORTER",
    "CB_TRANSLATE",
    "build_schedule_picker_keyboard",
    "handle_approve",
    "handle_delete",
    "handle_edit_request",
    "handle_regen",
    "handle_reject",
    "send_for_review",
    # Helpers used by review agent
    "build_review_keyboard",
    "extract_source_btn_data",
]


# ── Telegram keyboard builders ──


def build_review_keyboard(
    post_id: int,
    source_items: list[dict[str, str]] | None = None,
    channel_name: str = "",
    channel_username: str | None = None,
) -> InlineKeyboardMarkup:
    """Build inline keyboard for post review."""
    from app.presentation.telegram.utils.callback_data import ReviewAction

    main_row = [
        InlineKeyboardButton(text="✅ Approve", callback_data=ReviewAction(action="approve", post_id=post_id).pack()),
        InlineKeyboardButton(text="⏰ Schedule", callback_data=ReviewAction(action="schedule", post_id=post_id).pack()),
        InlineKeyboardButton(text="❌ Reject", callback_data=ReviewAction(action="reject", post_id=post_id).pack()),
        InlineKeyboardButton(text="🗑 Delete", callback_data=ReviewAction(action="delete", post_id=post_id).pack()),
    ]
    rows: list[list[InlineKeyboardButton]] = [
        main_row,
        [
            InlineKeyboardButton(
                text="✂️ Shorter", callback_data=ReviewAction(action="shorter", post_id=post_id).pack()
            ),
            InlineKeyboardButton(text="📝 Longer", callback_data=ReviewAction(action="longer", post_id=post_id).pack()),
            InlineKeyboardButton(text="🔄 Regen", callback_data=ReviewAction(action="regen", post_id=post_id).pack()),
        ],
    ]

    if channel_name:
        if channel_username:
            rows.append([InlineKeyboardButton(text=f"📢 {channel_name}", url=f"https://t.me/{channel_username}")])
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"📢 {channel_name}",
                        callback_data=ReviewAction(action="noop", post_id=post_id).pack(),
                    )
                ]
            )

    if source_items:
        source_buttons = [
            InlineKeyboardButton(text=f"📰 {item['title'][:25]}", url=item["url"])
            for item in source_items[:3]
            if item.get("url")
        ]
        if source_buttons:
            rows.append(source_buttons)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_schedule_picker_keyboard(
    post_id: int,
    available_slots: list[Any],
) -> InlineKeyboardMarkup:
    """Build time picker for scheduling. Shows next 5 available slots."""
    from app.presentation.telegram.utils.callback_data import PublishNow, ReviewAction, SchedulePick

    rows: list[list[InlineKeyboardButton]] = []
    for slot in available_slots[:5]:
        label = slot.strftime("%d %b %H:%M UTC")
        ts = int(calendar.timegm(slot.timetuple()))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📅 {label}",
                    callback_data=SchedulePick(post_id=post_id, ts=ts).pack(),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="🚀 Publish now", callback_data=PublishNow(post_id=post_id).pack()),
            InlineKeyboardButton(text="⬅️ Back", callback_data=ReviewAction(action="back", post_id=post_id).pack()),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Telegram message send/edit helpers ──


async def _send_review_message(
    bot: Bot,
    chat_id: int | str,
    text: str,
    keyboard: InlineKeyboardMarkup,
    image_url: str | None = None,
) -> Message:
    """Send review message — photo with caption if image available, else text.

    NOTE: parse_mode=None is required to override the bot's default parse_mode="HTML",
    otherwise caption_entities / entities are silently ignored by Telegram.
    """
    plain, entities = md_to_entities(text)

    if image_url and len(plain) <= 1024:
        try:
            photo = URLInputFile(image_url)
            return await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=plain,
                caption_entities=entities,
                reply_markup=keyboard,
                parse_mode=None,
            )
        except Exception:
            logger.exception("review_photo_failed_fallback_to_text")

    return await bot.send_message(
        chat_id=chat_id,
        text=plain,
        entities=entities,
        reply_markup=keyboard,
        disable_web_page_preview=True,
        parse_mode=None,
    )


async def _edit_review_message(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    text: str,
    entities: list[Any],
    keyboard: InlineKeyboardMarkup,
) -> None:
    """Edit a review message — handles both text messages and photo captions.

    NOTE: parse_mode=None overrides bot default to let entities work.
    """
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            entities=entities,
            reply_markup=keyboard,
            parse_mode=None,
        )
    except Exception as exc:
        if "message can't be edited" in str(exc).lower() or "there is no text" in str(exc).lower():
            caption = text[:1024]
            cap_entities = [e for e in entities if e.offset + e.length <= len(caption.encode("utf-16-le")) // 2]
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                caption_entities=cap_entities,
                reply_markup=keyboard,
                parse_mode=None,
            )
        else:
            raise


# ── Public API (same signatures as before — callers don't need to change) ──


async def send_for_review(
    bot: Bot,
    review_chat_id: int | str,
    channel_id: str,
    post: GeneratedPost,
    source_items: list[ContentItem],
    session_maker: async_sessionmaker[AsyncSession],
    *,
    api_key: str = "",
    embedding_model: str = "",
    channel_name: str = "",
    channel_username: str | None = None,
) -> int | None:
    """Send a generated post to the review channel with inline buttons.

    Creates a ChannelPost record in DB and returns its ID.
    """
    async with session_maker() as session:
        try:
            db_post = await create_review_post(
                channel_id=channel_id,
                post=post,
                source_items=source_items,
                review_chat_id=review_chat_id,
                session=session,
                api_key=api_key,
                embedding_model=embedding_model,
                session_maker=session_maker,
            )
            post_id = db_post.id

            source_btn_data: list[dict[str, str]] = []
            for s in source_items[:2]:
                if s.url:
                    source_btn_data.append({"title": s.title[:25], "url": s.url})

            keyboard = build_review_keyboard(
                post_id,
                source_items=source_btn_data,
                channel_name=channel_name,
                channel_username=channel_username,
            )

            msg = await _send_review_message(bot, review_chat_id, post.text, keyboard, post.image_url)
            db_post.review_message_id = msg.message_id
            await session.commit()
            logger.info("review_sent", post_id=post_id, review_msg=msg.message_id)
            return post_id
        except Exception:
            logger.exception("review_send_error", review_chat_id=review_chat_id)
            await session.rollback()
            return None


async def handle_approve(
    bot: Bot,
    post_id: int,
    channel_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Approve and publish a post immediately. Returns status message."""
    from app.agent.channel.publisher import publish_post as _publish

    async def _publish_fn(ch_id: int | str, gen_post: Any) -> int | None:
        return await _publish(bot, ch_id, gen_post)

    status_msg, _ = await approve_post(post_id, channel_id, _publish_fn, session_maker)
    return status_msg


async def handle_reject(
    post_id: int,
    session_maker: async_sessionmaker[AsyncSession],
    reason: str | None = None,
) -> str:
    """Reject a post."""
    return await reject_post(post_id, session_maker, reason)


async def handle_delete(
    bot: Bot,
    post_id: int,
    review_chat_id: int | str,
    review_message_id: int | None,
    session_maker: async_sessionmaker[AsyncSession],
) -> str:
    """Delete a post from DB and remove the review message from chat."""
    status_msg, deleted_info = await delete_post(post_id, session_maker)

    # Remove review message from chat (Telegram-specific)
    if deleted_info and review_message_id:
        try:
            await bot.delete_message(chat_id=review_chat_id, message_id=review_message_id)
        except Exception:
            logger.warning("review_message_delete_failed", post_id=post_id, exc_info=True)

    return status_msg


async def handle_edit_request(
    bot: Bot,
    post_id: int,
    instruction: str,
    api_key: str,
    model: str,
    review_chat_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    http_timeout: int = 30,
    temperature: float = 0.3,
    footer: str = "",
    channel_name: str = "",
    channel_username: str | None = None,
) -> str:
    """Edit a post based on admin instruction. Updates the review message."""
    status_msg, updated_post = await edit_post_text(
        post_id=post_id,
        instruction=instruction,
        api_key=api_key,
        model=model,
        session_maker=session_maker,
        http_timeout=http_timeout,
        temperature=temperature,
        footer=footer,
    )

    # Update Telegram review message if edit succeeded
    if updated_post and updated_post.review_message_id:
        source_btn_data = extract_source_btn_data(updated_post)
        keyboard = build_review_keyboard(
            post_id,
            source_items=source_btn_data,
            channel_name=channel_name,
            channel_username=channel_username,
        )
        try:
            review_plain, review_entities = md_to_entities(updated_post.post_text)
            await _edit_review_message(
                bot,
                review_chat_id,
                updated_post.review_message_id,
                review_plain,
                review_entities,
                keyboard,
            )
        except Exception:
            logger.exception("review_update_error")

    return status_msg


async def handle_regen(
    bot: Bot,
    post_id: int,
    api_key: str,
    model: str,
    language: str,
    review_chat_id: int | str,
    session_maker: async_sessionmaker[AsyncSession],
    *,
    footer: str = "",
    channel_name: str = "",
    channel_username: str | None = None,
) -> str:
    """Regenerate a post from its original sources."""
    status_msg, updated_post = await regen_post_text(
        post_id=post_id,
        api_key=api_key,
        model=model,
        language=language,
        session_maker=session_maker,
        footer=footer,
    )

    # Update Telegram review message if regen succeeded
    if updated_post and updated_post.review_message_id:
        source_btn_data = extract_source_btn_data(updated_post)
        keyboard = build_review_keyboard(
            post_id,
            source_items=source_btn_data,
            channel_name=channel_name,
            channel_username=channel_username,
        )
        try:
            regen_plain, regen_entities = md_to_entities(updated_post.post_text)
            await _edit_review_message(
                bot,
                review_chat_id,
                updated_post.review_message_id,
                regen_plain,
                regen_entities,
                keyboard,
            )
        except Exception:
            logger.exception("review_update_error")

    return status_msg
