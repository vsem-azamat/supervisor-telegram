from urllib.parse import quote

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import magic_link_store
from app.db.repositories import AdminRepository
from app.db.session import create_session_maker
from app.presentation.telegram.utils import buttons as buttons_service
from app.presentation.telegram.utils import other

router = Router()


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

    is_admin = message.from_user.id in settings.admin.super_admins or await admin_repo.is_admin(message.from_user.id)
    if is_admin:
        text += (
            "\n\n<b>👮 Команды для админов:</b>\n"
            "• /mute - замутить пользователя\n"
            "• /unmute - размутить пользователя\n"
            "• /ban - бан и добавить в ЧС\n"
            "• /unban - убрать из ЧС\n"
            "• /black - занести в ЧС всех чатов\n"
            "• /blacklist - посмотреть ЧС (с пагинацией)\n"
            "• /blacklist @username - найти пользователя в ЧС\n"
            "• /welcome &lt;text&gt; - изменить приветствие\n"
            "• /admin - добавить админа (ответом)\n"
            "• /unadmin - убрать админа (ответом)\n"
            "• /json - получить JSON сообщения\n"
        )
        if settings.admin.super_admins and message.from_user.id == settings.admin.super_admins[0]:
            text += "• /adminlink - одноразовая ссылка в web-админку\n"

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
    if not settings.admin.super_admins or message.from_user.id != settings.admin.super_admins[0]:
        await message.answer("Команда доступна только главному администратору.")
        return
    if settings.webapi.auth_mode != "magic_link":
        await message.answer("WEBAPI_AUTH_MODE=magic_link не включен.")
        return

    session_maker = create_session_maker()
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
