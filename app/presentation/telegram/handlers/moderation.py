from aiogram import Bot, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services import moderation as moderation_services
from app.application.services import spam as spam_service
from app.application.services.user_service import UserService
from app.infrastructure.db.repositories import (
    ChatRepository,
    MessageRepository,
)
from app.presentation.telegram.logger import logger
from app.presentation.telegram.utils import BlacklistConfirm, BlacklistPagination, UnblockUser, other
from app.presentation.telegram.utils.blacklist import (
    build_blacklist_keyboard,
    build_blacklist_text,
    build_user_details_keyboard,
    build_user_details_text,
)

moderation_router = Router()


def reply_required_error(action: str) -> str:
    """Standard error when a command should be a reply."""
    return f"Примените команду ответом на сообщение пользователя, которого нужно {action}. 🙏"


def is_user_check_error() -> str:
    """Standard error when target message does not contain a user."""
    return "🚫 Это не пользователь или что-то пошло не так."


@moderation_router.message(Command("mute", prefix="!/"))
async def mute_user(message: types.Message, bot: Bot) -> None:
    # Ensure command is used as a reply
    if not message.reply_to_message:
        await message.answer(reply_required_error("замутить"))
        await message.delete()
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    mute_guide = (
        "Для мута пользователя используйте команду в формате:\n\n"
        "<code>!mute [время] [единица времени]</code>\n\n"
        "Примеры:\n<code>!mute 5m</code> - на 5 минут\n"
        "<code>!mute 1h</code> - на 1 час\n"
        "<code>!mute 1d</code> - на 1 день\n"
        "<code>!mute 1w</code> - на 1 неделю"
    )

    # Parse and validate mute duration
    try:
        if not message.text:
            await message.answer("Команда не может быть пустой.")
            return
        mute_duration = other.calculate_mute_duration(message.text)
    except Exception:
        answer = await message.answer(f"Мне не удалось распознать время мута!\n\n{mute_guide}")
        await message.delete()
        await other.sleep_and_delete(answer, 10)
        return

    # Set permissions to mute the user
    read_only_permissions = types.ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
    )

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            message.reply_to_message.from_user.id,
            permissions=read_only_permissions,
            until_date=mute_duration.until_date,
        )
        mention = await other.get_user_mention(message.reply_to_message.from_user)
        text_mute = (
            f"{mention} в муте на {mute_duration.time} {mute_duration.unit}!\n\n"
            f"Дата размута: {mute_duration.formatted_until_date()}"
        )
        await message.reply_to_message.reply(text_mute)
        await message.delete()

    except Exception as err:
        await message.answer(f"Произошла ошибка:\n\n{err}")
        logger.error(f"Error while muting user: {err}")


@moderation_router.message(Command("unmute", prefix="!/"))
async def unmute_user(message: types.Message) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("размутить"))
        await message.delete()
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    # Reset permissions to default chat permissions
    default_permissions = message.chat.permissions
    if not default_permissions:
        await message.answer("Похоже, что я нахожусь не в чате или у меня нет прав администратора.")
        return

    try:
        await message.chat.restrict(
            user_id=message.reply_to_message.from_user.id,
            permissions=default_permissions,
            until_date=0,
        )
        mention = await other.get_user_mention(message.reply_to_message.from_user)
        await message.answer(f"Пользователь {mention} размучен!")
    except Exception as err:
        await message.answer(f"Произошла ошибка:\n\n{err}")


@moderation_router.message(Command("ban", prefix="!/"))
async def ban_user(message: types.Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("забанить"))
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        mention = await other.get_user_mention(message.reply_to_message.from_user)
        await message.answer(f"Пользователь {mention} забанен")
    except Exception as err:
        error_msg = await message.answer(f"Что-то пошло не так:\n\n{err}")
        await other.sleep_and_delete(error_msg, 10)

    await message.delete()


@moderation_router.message(Command("unban", prefix="!/"))
async def unban_user(message: types.Message, bot: Bot) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("разбанить"))
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        return

    try:
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        mention = await other.get_user_mention(message.reply_to_message.from_user)
        await message.answer(f"Пользователь {mention} разбанен")
    except Exception as err:
        error_msg = await message.answer(f"Что-то пошло не так:\n\n{err}")
        await other.sleep_and_delete(error_msg, 10)

    await message.delete()


@moderation_router.message(Command("black", prefix="!/"))
async def full_ban(message: types.Message, message_repo: MessageRepository, db: AsyncSession) -> None:
    if not message.reply_to_message:
        await message.answer(reply_required_error("добавить в черный список"))
        return

    if not message.reply_to_message.from_user:
        await message.answer(is_user_check_error())
        logger.warning(f"User {message.reply_to_message.from_user} is not a user.")
        return

    target = message.reply_to_message
    if not target.from_user:
        await message.answer(is_user_check_error())
        return
    id_user = target.from_user.id
    chats_count = await message_repo.count_user_chats(id_user)
    messages_count = await message_repo.count_user_messages(id_user)
    spam_flag = await spam_service.detect_spam(db, target)

    info_text = (
        "<b>Вы уверены?</b>\n\n"
        "<b>Информация:</b>\n"
        f"- {chats_count} чатов\n"
        f"- {messages_count} сообщений\n"
        f"- {'спам обнаружен' if spam_flag else 'спам не обнаружен'}"
    )
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Yes",
        callback_data=BlacklistConfirm(
            user_id=id_user,
            chat_id=target.chat.id,
            message_id=target.message_id,
        ).pack(),
    )
    builder.button(text="No", callback_data="cancel_blacklist")
    builder.adjust(2)
    await message.answer(info_text, reply_markup=builder.as_markup())
    await message.delete()


@moderation_router.message(Command("spam", prefix="!/"))
async def label_spam(message: types.Message, message_repo: MessageRepository, db: AsyncSession) -> None:
    if not message.reply_to_message:
        answer = await message.answer(reply_required_error("пометить как спам"))
        await message.delete()
        await other.sleep_and_delete(answer, 10)
        return

    target = message.reply_to_message
    if not target.from_user:
        await message.answer(is_user_check_error())
        return
    spammer_user_id = target.from_user.id
    chats_count = await message_repo.count_user_chats(spammer_user_id)
    messages_count = await message_repo.count_user_messages(spammer_user_id)
    spam_flag = await spam_service.detect_spam(db, target)

    info_text = (
        "<b>Вы уверены?</b>\n\n"
        "<b>Информация:</b>\n"
        f"- {chats_count} чатов\n"
        f"- {messages_count} сообщений\n"
        f"- {'спам обнаружен' if spam_flag else 'спам не обнаружен'}"
    )
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Yes",
        callback_data=BlacklistConfirm(
            user_id=spammer_user_id,
            chat_id=target.chat.id,
            message_id=target.message_id,
            revoke=1,
            mark_spam=1,
        ).pack(),
    )
    builder.button(text="No", callback_data="cancel_blacklist")
    builder.adjust(2)
    await message.answer(info_text, reply_markup=builder.as_markup())
    await message.delete()


@moderation_router.message(Command("welcome", prefix="!/"))
async def welcome_change(message: types.Message, chat_repo: ChatRepository) -> None:
    if not message.text:
        await message.answer("Сообщение не может быть пустым.")
        return
    welcome_message = message.text.partition(" ")[2]
    await chat_repo.update_welcome_message(message.chat.id, welcome_message)
    await message.answer("<b>Приветственное сообщение изменено!</b>")
    await message.answer(welcome_message)
    await message.delete()


@moderation_router.message(Command("autodelete_joinleave", prefix="!/"))
async def toggle_autodelete_joinleave(message: types.Message, chat_repo: ChatRepository) -> None:
    """Toggle auto-deletion of join/leave messages."""
    chat = await chat_repo.get_by_id(message.chat.id)

    if not chat:
        # Create chat entity if it doesn't exist
        from app.domain.entities import ChatEntity

        chat = ChatEntity(
            id=message.chat.id,
            title=message.chat.title or f"Chat {message.chat.id}",
            auto_delete_join_leave=False,  # default value
        )
        chat = await chat_repo.save(chat)

    # Toggle the setting using entity method
    chat.toggle_auto_delete_join_leave()
    await chat_repo.save(chat)

    status = "включено" if chat.auto_delete_join_leave else "выключено"
    await message.answer(f"<b>Автоудаление сообщений о входе/выходе {status}!</b>")
    await message.delete()


@moderation_router.callback_query(BlacklistConfirm.filter())
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
        logger.warning(f"Failed to delete message {message_id}: {err}")

    try:
        if not callback.message or not isinstance(callback.message, types.Message):
            await callback.answer("Не удалось получить сообщение.")
            return
        await bot.ban_chat_member(callback.message.chat.id, user_id)
        member = await bot.get_chat_member(callback.message.chat.id, user_id)
        mention = await other.get_user_mention(member.user)
        await moderation_services.add_to_blacklist(db, bot, user_id, revoke_messages=revoke)
        await callback.message.edit_text(f"{mention} добавлен в черный список.")
    except Exception as err:
        if callback.message and isinstance(callback.message, types.Message):
            await callback.message.edit_text(f"Произошла ошибка:\n\n{err}")
        logger.error(f"Error while adding user {user_id} to blacklist: {err}")

    await callback.answer()


@moderation_router.callback_query(lambda c: c.data == "cancel_blacklist")
async def process_blacklist_cancel(callback: types.CallbackQuery) -> None:
    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.edit_text("Действие отменено")
    await callback.answer()


@moderation_router.message(Command("blacklist", prefix="!/"))
async def show_blacklist(message: types.Message, user_service: UserService) -> None:
    """Show blacklist with pagination or search for specific user."""
    command_args = message.text.split()[1:] if message.text else []

    # Search for specific user if argument provided
    if command_args:
        identifier = command_args[0]
        user = await user_service.find_blocked_user(identifier)

        if not user:
            await message.answer(f"User <code>{identifier}</code> not found in blacklist")
            await message.delete()
            return

        # Show individual user details
        text = build_user_details_text(user)
        keyboard = build_user_details_keyboard(user)

        await message.answer(text, reply_markup=keyboard.as_markup())
        await message.delete()
        return

    # Show paginated blacklist
    await _show_blacklist_page(message, user_service, page=0)


async def _show_blacklist_page(
    message: types.Message, user_service: UserService, page: int = 0, query: str = ""
) -> None:
    """Display blacklist page with pagination."""
    blocked_users = await user_service.get_blocked_users()

    if not blocked_users:
        await message.answer("Blacklist is empty")
        await message.delete()
        return

    page_size = 10
    total_pages = (len(blocked_users) + page_size - 1) // page_size

    # Ensure page is within bounds
    page = max(0, min(page, total_pages - 1))

    text = build_blacklist_text(len(blocked_users), page, total_pages, page_size, query)
    keyboard = build_blacklist_keyboard(blocked_users, page, total_pages, page_size, query)

    await message.answer(text, reply_markup=keyboard.as_markup())
    await message.delete()


@moderation_router.callback_query(BlacklistPagination.filter())
async def handle_blacklist_pagination(
    callback: types.CallbackQuery,
    callback_data: BlacklistPagination,
    user_service: UserService,
) -> None:
    """Handle blacklist pagination callbacks."""
    await callback.answer()

    if not callback.message:
        return

    blocked_users = await user_service.get_blocked_users()
    page_size = 10
    total_pages = (len(blocked_users) + page_size - 1) // page_size

    # Ensure page is within bounds
    page = max(0, min(callback_data.page, total_pages - 1))

    text = build_blacklist_text(len(blocked_users), page, total_pages, page_size, callback_data.query)
    keyboard = build_blacklist_keyboard(blocked_users, page, total_pages, page_size, callback_data.query)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
    except TelegramBadRequest:
        # Fallback to sending new message if edit fails
        await callback.message.answer(text, reply_markup=keyboard.as_markup())


@moderation_router.callback_query(UnblockUser.filter())
async def unblock_user_callback(
    callback: types.CallbackQuery,
    callback_data: UnblockUser,
    bot: Bot,
    db: AsyncSession,
) -> None:
    user_id = callback_data.user_id
    await moderation_services.remove_from_blacklist(db, bot, user_id)
    try:
        if not callback.message or not isinstance(callback.message, types.Message):
            await callback.answer("Не удалось получить сообщение.")
            return
        member = await bot.get_chat_member(callback.message.chat.id, user_id)
        user = member.user
        user_identifier = user.username or user.first_name or str(user.id)
    except Exception:
        # Fallback: user not found, use ID as identifier
        user_identifier = str(user_id)

    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.edit_text(f"Пользователь {user_identifier} разблокирован")
    await callback.answer()
