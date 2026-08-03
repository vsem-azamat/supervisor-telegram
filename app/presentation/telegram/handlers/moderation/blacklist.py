"""Banning somebody out of every chat, and reading back who is out.

`/banall` acts, `/blacklist` shows. They used to be `!black` and `!blacklist`,
four letters apart, one of them irreversible across forty-five chats — and
`!spam` was a third name for `!black` that also wiped the person's messages.
All three sent the same confirmation dialog, so the screen in front of an
administrator could not tell them which command they had typed.

Now the choice between the two outcomes is made on a labelled button, at the
moment of deciding, rather than in the spelling of a word a minute earlier.
"""

from aiogram import Bot, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ModerationEventAction, ModerationEventSource
from app.core.logging import get_logger
from app.core.text import escape_html
from app.db.repositories import MessageRepository
from app.moderation import audit, spam_service
from app.moderation import blacklist as moderation_services
from app.moderation.user_service import UserService
from app.presentation.telegram.handlers.moderation._common import (
    is_user_check_error,
    reply_required_error,
)
from app.presentation.telegram.utils import BlacklistConfirm, BlacklistPagination, UnblockUser, other
from app.presentation.telegram.utils.blacklist import (
    build_blacklist_keyboard,
    build_blacklist_text,
    build_user_details_keyboard,
    build_user_details_text,
)

logger = get_logger("handler.moderation.blacklist")
router = Router()

_BLACKLIST_PAGE_SIZE = 10


@router.message(Command("banall", prefix="!/"))
async def ban_everywhere(message: types.Message, message_repo: MessageRepository, db: AsyncSession) -> None:
    """Ask before removing somebody from every chat.

    The dialog exists to be read, so it carries the three things that argue for
    or against the ban — how widely the person is present, how much they have
    written, and what the spam filter makes of the message being replied to.
    A filter that stayed quiet is as much information as one that fired.
    """
    if not message.reply_to_message:
        await message.answer(reply_required_error("забанить во всех чатах"))
        return

    target = message.reply_to_message
    if not target.from_user:
        await message.answer(is_user_check_error())
        logger.warning("blacklist_target_not_user", chat_id=message.chat.id)
        return

    id_user = target.from_user.id
    chats_count = await message_repo.count_user_chats(id_user)
    messages_count = await message_repo.count_user_messages(id_user)
    spam_flag = await spam_service.detect_spam(db, target)

    info_text = (
        "<b>Забанить во всех чатах?</b>\n"
        f"{other.get_user_mention(target.from_user)} · <code>{id_user}</code>\n\n"
        f"Замечен в {chats_count} чатах, {messages_count} сообщений.\n"
        f"Спам-фильтр: <b>{'сработал' if spam_flag else 'не сработал'}</b>.\n\n"
        "Бан снимается только вручную, через /blacklist. "
        "Стирание сообщений заодно учит спам-фильтр."
    )

    common = {"user_id": id_user, "chat_id": target.chat.id, "message_id": target.message_id}
    builder = InlineKeyboardBuilder()
    builder.button(text="Забанить везде", callback_data=BlacklistConfirm(**common).pack())
    builder.button(
        # The count comes from our own record of what the person wrote, which is
        # what we would try to delete. Telegram refuses some of them, so this is
        # the size of the attempt rather than a promise.
        text=f"Забанить и стереть сообщения ({messages_count})",
        callback_data=BlacklistConfirm(**common, revoke=1, mark_spam=1).pack(),
    )
    builder.button(text="Отмена", callback_data="cancel_blacklist")
    builder.adjust(1)
    await message.answer(info_text, reply_markup=builder.as_markup())
    await message.delete()


@router.message(Command("black", "spam", prefix="!"))
async def moved_to_banall(message: types.Message) -> None:
    """The old names answer instead of acting.

    Deleting the handlers outright would leave `!spam` unhandled, and an
    unhandled command looks exactly like a command that worked — which, for the
    one command in this bot that wipes a person's messages across every chat, is
    the wrong thing for silence to mean.
    """
    answer = await message.answer(
        "Команда переехала: теперь <b>/banall</b>.\nСтирать сообщения или нет — выбирается кнопкой в подтверждении."
    )
    await message.delete()
    other.sleep_and_delete(answer, 30)


@router.callback_query(BlacklistConfirm.filter())
async def process_blacklist_confirm(
    callback: types.CallbackQuery,
    callback_data: BlacklistConfirm,
    bot: Bot,
    db: AsyncSession,
    message_repo: MessageRepository,
) -> None:
    user_id = callback_data.user_id
    chat_id = callback_data.chat_id
    message_id = callback_data.message_id
    revoke = bool(callback_data.revoke)
    mark_spam = bool(callback_data.mark_spam)

    if mark_spam:
        await message_repo.label_spam(chat_id=chat_id, message_id=message_id)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as err:
        logger.warning("message_delete_failed", error=str(err), message_id=message_id, chat_id=chat_id)

    try:
        if not callback.message or not isinstance(callback.message, types.Message):
            await callback.answer("Не удалось получить сообщение.")
            return
        await bot.ban_chat_member(callback.message.chat.id, user_id)
        member = await bot.get_chat_member(callback.message.chat.id, user_id)
        mention = other.get_user_mention(member.user)
        await moderation_services.add_to_blacklist(db, bot, user_id, revoke_messages=revoke)
        # No chat: the entry holds everywhere, and the ban just carried out in
        # this one is a consequence of it rather than a separate decision.
        await audit.record(
            db,
            action=ModerationEventAction.BLACKLIST,
            source=ModerationEventSource.COMMAND,
            actor_id=callback.from_user.id,
            target_user_id=user_id,
            detail="спам" if mark_spam else None,
        )
        from app.presentation.telegram.middlewares.black_list import invalidate_blacklist_cache

        invalidate_blacklist_cache()
        await callback.message.edit_text(f"{mention} добавлен в черный список.")
    except Exception as err:
        if callback.message and isinstance(callback.message, types.Message):
            await callback.message.edit_text("Произошла ошибка. Попробуйте позже.")
        logger.error("blacklist_add_failed", error=str(err), user_id=user_id, chat_id=chat_id)

    await callback.answer()


@router.callback_query(lambda c: c.data == "cancel_blacklist")
async def process_blacklist_cancel(callback: types.CallbackQuery) -> None:
    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.edit_text("Действие отменено")
    await callback.answer()


@router.message(Command("blacklist", prefix="!/"))
async def show_blacklist(message: types.Message, user_service: UserService) -> None:
    """Show blacklist with pagination or search for specific user."""
    command_args = message.text.split()[1:] if message.text else []

    if command_args:
        identifier = command_args[0]
        user = await user_service.find_blocked_user(identifier)

        if not user:
            await message.answer(f"<code>{escape_html(identifier)}</code> в чёрном списке не найден.")
            await message.delete()
            return

        text = build_user_details_text(user)
        keyboard = build_user_details_keyboard(user)

        await message.answer(text, reply_markup=keyboard.as_markup())
        await message.delete()
        return

    await _show_blacklist_page(message, user_service, page=0)


async def _show_blacklist_page(
    message: types.Message, user_service: UserService, page: int = 0, query: str = ""
) -> None:
    """Display blacklist page with pagination."""
    blocked_users = await user_service.get_blocked_users()

    if not blocked_users:
        await message.answer("Чёрный список пуст.")
        await message.delete()
        return

    total_pages = (len(blocked_users) + _BLACKLIST_PAGE_SIZE - 1) // _BLACKLIST_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    text = build_blacklist_text(len(blocked_users), page, total_pages, _BLACKLIST_PAGE_SIZE, query)
    keyboard = build_blacklist_keyboard(blocked_users, page, total_pages, _BLACKLIST_PAGE_SIZE, query)

    await message.answer(text, reply_markup=keyboard.as_markup())
    await message.delete()


@router.callback_query(BlacklistPagination.filter())
async def handle_blacklist_pagination(
    callback: types.CallbackQuery,
    callback_data: BlacklistPagination,
    user_service: UserService,
) -> None:
    """Handle blacklist pagination callbacks."""
    await callback.answer()

    if not isinstance(callback.message, types.Message):
        return

    blocked_users = await user_service.get_blocked_users()
    total_pages = (len(blocked_users) + _BLACKLIST_PAGE_SIZE - 1) // _BLACKLIST_PAGE_SIZE
    page = max(0, min(callback_data.page, total_pages - 1))

    text = build_blacklist_text(len(blocked_users), page, total_pages, _BLACKLIST_PAGE_SIZE, callback_data.query)
    keyboard = build_blacklist_keyboard(blocked_users, page, total_pages, _BLACKLIST_PAGE_SIZE, callback_data.query)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=keyboard.as_markup())


@router.callback_query(UnblockUser.filter())
async def unblock_user_callback(
    callback: types.CallbackQuery,
    callback_data: UnblockUser,
    bot: Bot,
    db: AsyncSession,
) -> None:
    user_id = callback_data.user_id
    await moderation_services.remove_from_blacklist(db, bot, user_id)
    await audit.record(
        db,
        action=ModerationEventAction.UNBLACKLIST,
        source=ModerationEventSource.COMMAND,
        actor_id=callback.from_user.id,
        target_user_id=user_id,
    )
    from app.presentation.telegram.middlewares.black_list import invalidate_blacklist_cache

    invalidate_blacklist_cache()
    try:
        if not callback.message or not isinstance(callback.message, types.Message):
            await callback.answer("Не удалось получить сообщение.")
            return
        member = await bot.get_chat_member(callback.message.chat.id, user_id)
        user = member.user
        user_identifier = user.username or user.first_name or str(user.id)
    except Exception:
        user_identifier = str(user_id)

    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.edit_text(f"Пользователь {escape_html(user_identifier)} разблокирован")
    await callback.answer()
