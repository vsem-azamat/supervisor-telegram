from urllib.parse import quote

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db import magic_link_store
from app.db.repositories import AdminRepository
from app.db.session import get_session_maker
from app.presentation.telegram.utils import buttons as buttons_service
from app.presentation.telegram.utils import other

router = Router()
logger = get_logger("handlers.start")


@router.message(Command("start", "help", prefix="/!"))
async def start_private(message: types.Message, admin_repo: AdminRepository) -> None:
    if not message.from_user:
        return

    text = (
        "<b>🤖 Привет!</b>\n"
        "Я модерирую чаты по Чехии!\n\n"
        "📚 <b>Команды:</b>\n"
        "• /chats - список чатов\n"
        "• /contacts - контакты\n"
        "• /help - помощь\n"
        "• /report - пожаловаться (нужно переслать сообщение)\n"
    )

    is_super_admin = message.from_user.id in settings.admin.super_admins
    if is_super_admin or await admin_repo.is_admin(message.from_user.id):
        chats = await admin_repo.chats_for(message.from_user.id)
        where = "во всех чатах" if is_super_admin else f"в ваших чатах ({len(chats)})"
        text += (
            f"\n\n<b>👮 Команды модератора</b> — {where}:\n"
            "• /mute - замутить пользователя\n"
            "• /unmute - размутить пользователя\n"
            "• /kick - удалить из чата (сможет вернуться)\n"
            "• /ban - забанить в этом чате\n"
            "• /unban - разбанить в этом чате\n"
            "• /info - что известно о пользователе\n"
            "• /del - удалить сообщение (ответом)\n"
            "• /purge - удалить пачку до этого сообщения\n"
            "• /pin, /unpin - закрепить и открепить\n"
            "• /welcome &lt;text&gt; - изменить приветствие\n"
        )

    if is_super_admin:
        text += (
            "\n<b>🔑 Команды главного администратора</b> — действуют на все чаты:\n"
            "• /black - занести в ЧС всех чатов\n"
            "• /blacklist - посмотреть ЧС (с пагинацией)\n"
            "• /blacklist @username - найти пользователя в ЧС\n"
            "• /admin - назначить модератора этого чата (ответом)\n"
            "• /unadmin - снять модератора этого чата (ответом)\n"
            "• /json - получить JSON сообщения\n"
            "• /adminlink - одноразовая ссылка в web-админку\n"
        )

    builder = await buttons_service.get_contacts_buttons()
    bot_message = await message.answer(
        text,
        disable_web_page_preview=True,
        reply_markup=builder.as_markup(),
    )
    await message.delete()
    other.sleep_and_delete(bot_message)


@router.message(Command("adminlink", "webadmin", prefix="/!"))
async def generate_admin_magic_link(message: types.Message) -> None:
    if not message.from_user:
        return
    if message.chat.type != "private":
        await message.answer("Команда доступна только в личке с ботом.")
        return
    # Every super administrator, not just the first one listed: the web console
    # admits all of them, and a link one of them cannot ask for is a lockout.
    if message.from_user.id not in settings.admin.super_admins:
        await message.answer("Команда доступна только главным администраторам.")
        return
    if settings.webapi.auth_mode != "magic_link":
        await message.answer("WEBAPI_AUTH_MODE=magic_link не включен.")
        return

    session_maker = get_session_maker()
    async with session_maker() as session:
        token, _ = await magic_link_store.create_magic_link(
            session,
            user_id=message.from_user.id,
            ttl_minutes=settings.webapi.magic_link_ttl_minutes,
        )

    if settings.webapi.public_url:
        url = f"{settings.webapi.public_url.rstrip('/')}/login#token={quote(token)}"
        await message.answer(
            "Одноразовая ссылка для входа в web-админку:\n"
            f"{url}\n\n"
            f"Действует {settings.webapi.magic_link_ttl_minutes} минут."
        )
    else:
        await message.answer(
            "WEBAPI_PUBLIC_URL не настроен. Одноразовый токен для /login#token=:\n"
            f"{token}\n\n"
            f"Действует {settings.webapi.magic_link_ttl_minutes} минут."
        )


@router.message(Command("chats", prefix="/!"))
async def get_chats(message: types.Message, db: AsyncSession) -> None:
    text = "<b>Студенческие чаты:</b>\n\nПожалуйста, соблюдайте правила!\n\n"
    builder = await buttons_service.get_chat_buttons(db)
    bot_message = await message.answer(text, reply_markup=builder.as_markup())
    await message.delete()
    other.sleep_and_delete(bot_message)


@router.message(Command("contacts", prefix="/!"))
async def get_contacts(message: types.Message) -> None:
    text = "📞 <b>Контакты:</b>\n\n• 📧 <b>Сотрудничество:</b> @czech_media_admin\n• 🧑🏿‍💻 <b>Dev:</b> @vsem_azamat"
    bot_message = await message.answer(text)
    await message.delete()
    other.sleep_and_delete(bot_message)
