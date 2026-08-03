"""The front door: a greeting, a справочник, and the way into the console.

`/start` and `/help` were one handler answering one wall of text. That wall was
the first thing a first-year saw, it listed commands they could not run, it
never mentioned the site the whole catalogue lives on, and it deleted itself
after sixty seconds.

They are two questions. `/start` answers "what is this and where do I go" and
stays on screen; `/help` answers "what can I type" and still grows with the
role of whoever asked.
"""

from urllib.parse import quote

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.text import plural
from app.db import magic_link_store
from app.db.repositories import AdminRepository
from app.db.session import get_session_maker
from app.presentation.telegram.utils import buttons as buttons_service
from app.presentation.telegram.utils import other

router = Router()
logger = get_logger("handlers.start")

# Where somebody who wants to place an advertisement, or to say anything else,
# is sent. The bot answers questions about chats; a person answers the rest.
CONTACT_USERNAME = "czech_media_admin"


class AdminConsole(CallbackData, prefix="console"):
    """Press to be issued a one-time sign-in link.

    A URL button would have to carry a token minted when the menu was drawn,
    which starts expiring while the person is still reading the message it sits
    under. A callback mints it at the moment somebody actually wants it.
    """


def _site() -> str:
    return settings.webapi.public_url.rstrip("/")


@router.message(Command("start", prefix="/!"))
async def start_private(message: types.Message, admin_repo: AdminRepository) -> None:
    """Say what this is, and offer the two places worth going."""
    if not message.from_user:
        return

    text = (
        "<b>Konnekt</b>\n\n"
        "Каталог студенческих чатов Чехии — по университетам, факультетам "
        "и общежитиям. За ними следят модераторы, спам вычищается.\n\n"
    )

    is_super_admin = message.from_user.id in settings.admin.super_admins
    if is_super_admin:
        text += "Вы главный администратор. Все команды — /help"
    elif await admin_repo.is_admin(message.from_user.id):
        chats = await admin_repo.chats_for(message.from_user.id)
        moderates = plural(len(chats), "чат", "чата", "чатов")
        text += f"Вы модерируете {len(chats)} {moderates}. Все команды — /help"
    else:
        text += "Все команды — /help"

    builder = InlineKeyboardBuilder()
    if is_super_admin and settings.webapi.public_url:
        builder.button(text="⚙️ Открыть консоль", callback_data=AdminConsole().pack())
    if settings.webapi.public_url:
        builder.button(text="🔎 Найти свой чат", url=_site())
        builder.button(text="📣 Реклама в чатах", url=f"{_site()}/ads")
    builder.button(text="✉️ Написать нам", url=f"https://t.me/{CONTACT_USERNAME}")
    builder.adjust(1)

    # Deliberately not scheduled for deletion. This is the message somebody
    # comes back to; the справочник below is the one that may go.
    await message.answer(text, disable_web_page_preview=True, reply_markup=builder.as_markup())


@router.message(Command("help", prefix="/!"))
async def help_command(message: types.Message, admin_repo: AdminRepository) -> None:
    """List what this person, specifically, may type.

    Grouped by how far a mistake travels — one chat, or all of them. That split
    is the permission rule the routers already enforce, and a help text that
    grouped them any other way would teach the wrong shape.
    """
    if not message.from_user:
        return

    text = (
        "<b>Команды</b>\n\n"
        "<b>Всем</b>\n"
        "/chats — чаты списком\n"
        "/contacts — связаться\n"
        "/report — в ответ на сообщение, позвать модераторов (в группе)\n"
    )

    is_super_admin = message.from_user.id in settings.admin.super_admins
    if is_super_admin or await admin_repo.is_admin(message.from_user.id):
        if is_super_admin:
            where = "во всех чатах"
        else:
            chats = await admin_repo.chats_for(message.from_user.id)
            where = f"в ваших чатах ({len(chats)})"
        text += (
            f"\n<b>Модератору</b> — {where}\n"
            "/mute, /unmute — заглушить, вернуть голос\n"
            "/kick — удалить, сможет вернуться\n"
            "/ban, /unban — забанить в этом чате\n"
            "/del, /purge — удалить сообщение, удалить пачкой\n"
            "/pin, /unpin — закрепить, открепить\n"
            "/info — что известно о человеке\n"
            "/welcome &lt;текст&gt; — приветствие чата\n"
        )

    if is_super_admin:
        text += (
            "\n<b>Главному администратору</b> — во всех чатах сразу\n"
            "/banall — забанить везде, в ответ на сообщение\n"
            "/blacklist — чёрный список, поиск по нему\n"
            "/admin, /unadmin — назначить, снять модератора этого чата\n"
        )

    bot_message = await message.answer(text, disable_web_page_preview=True)
    await message.delete()
    other.sleep_and_delete(bot_message)


async def _mint_magic_link(user_id: int) -> str:
    session_maker = get_session_maker()
    async with session_maker() as session:
        token, _ = await magic_link_store.create_magic_link(
            session,
            user_id=user_id,
            ttl_minutes=settings.webapi.magic_link_ttl_minutes,
        )
    return token


@router.callback_query(AdminConsole.filter())
async def open_console(callback: types.CallbackQuery) -> None:
    """Issue a one-time sign-in link to whoever pressed.

    Checked here rather than trusted from the keyboard: the button is only
    drawn for super administrators, but the callback data is short, guessable,
    and arrives without the message that decided to draw it.
    """
    if callback.from_user.id not in settings.admin.super_admins:
        await callback.answer("Только для главных администраторов.", show_alert=True)
        return

    if not callback.message or not isinstance(callback.message, types.Message):
        await callback.answer()
        return

    if settings.webapi.auth_mode != "magic_link":
        await callback.message.answer("Вход по ссылке выключен: WEBAPI_AUTH_MODE=magic_link не задан.")
        await callback.answer()
        return

    token = await _mint_magic_link(callback.from_user.id)
    minutes = settings.webapi.magic_link_ttl_minutes

    if settings.webapi.public_url:
        await callback.message.answer(
            f"Одноразовая ссылка, действует {minutes} мин:\n"
            f"{_site()}/login#token={quote(token)}\n\n"
            "Не пересылайте — она входит без пароля.",
            disable_web_page_preview=True,
        )
    else:
        await callback.message.answer(
            f"WEBAPI_PUBLIC_URL не настроен. Токен для /login#token=:\n<code>{token}</code>\n\nДействует {minutes} мин."
        )
    await callback.answer()


@router.message(Command("chats", prefix="/!"))
async def get_chats(message: types.Message, db: AsyncSession) -> None:
    text = "<b>Студенческие чаты:</b>\n\nПожалуйста, соблюдайте правила!\n\n"
    builder = await buttons_service.get_chat_buttons(db)
    bot_message = await message.answer(text, reply_markup=builder.as_markup())
    await message.delete()
    other.sleep_and_delete(bot_message)


@router.message(Command("contacts", prefix="/!"))
async def get_contacts(message: types.Message) -> None:
    text = f"📞 <b>Контакты:</b>\n\n• 📧 <b>Сотрудничество:</b> @{CONTACT_USERNAME}\n• 🧑🏿‍💻 <b>Dev:</b> @vsem_azamat"
    bot_message = await message.answer(text)
    await message.delete()
    other.sleep_and_delete(bot_message)
