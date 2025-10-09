from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.core.config import settings
from app.core.logging import BotLogger
from app.infrastructure.ngrok_helper import get_current_ngrok_url

logger = BotLogger("webapp")
router = Router()


@router.message(F.text == "/webapp")
async def webapp_command(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None

    if not user_id:
        await message.answer("Ошибка: не удалось определить пользователя")
        return

    # Check if user is admin (you can expand this logic)
    if user_id not in settings.admin.super_admins:
        await message.answer("Доступ запрещен. Только для администраторов.")
        return

    # In development mode, try to get current ngrok URL dynamically
    # This solves the problem of ngrok URLs changing on each restart
    webapp_url = settings.webapp.url
    if settings.environment == "development":
        ngrok_url = await get_current_ngrok_url()
        if ngrok_url:
            webapp_url = ngrok_url
            logger.logger.info("Using dynamic ngrok URL for webapp", url=ngrok_url)
        else:
            logger.logger.warning("Could not fetch ngrok URL, using configured URL", url=webapp_url)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎛️ Открыть админ панель", web_app=WebAppInfo(url=webapp_url))]]
    )

    await message.answer(
        "Добро пожаловать в админ панель модератора!\n\n"
        "Нажмите кнопку ниже, чтобы открыть веб-интерфейс управления ботом.",
        reply_markup=keyboard,
    )

    logger.log_user_action(user_id=user_id, action="webapp_opened", chat_id=message.chat.id if message.chat else None)


@router.message(F.text == "/help_webapp")
async def webapp_help(message: Message) -> None:
    help_text = """
🎛️ **Веб-приложение модератора**

Команды для работы с веб-интерфейсом:
• `/webapp` - Открыть админ панель (только для администраторов)

Возможности веб-панели:
• Просмотр информации о пользователе
• Управление чатами и каналами
• Статистика и аналитика
• Настройки бота

💡 Веб-интерфейс работает только для авторизованных администраторов.
    """

    await message.answer(help_text, parse_mode="Markdown")
