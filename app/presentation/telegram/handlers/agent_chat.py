"""
Agent chat handler for private messages.

Provides two modes for super admins in private chat:
1. Normal bot mode (default) - responds to commands only
2. Agent mode - AI agent responds to all messages
"""

import logging
import time
from contextlib import suppress

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile

from app.application.services.agent_service import AgentService
from app.domain.agent import AgentModelConfig, AgentSession, ModelProvider
from app.domain.agent_models import OPENROUTER_MODELS
from app.presentation.telegram.utils.filters import ChatTypeFilter, SuperAdminFilter

logger = logging.getLogger(__name__)

router = Router()

# In-memory storage for agent mode state
# Maps user_id -> session_id
_agent_mode_users: dict[int, str] = {}

# Telegram message limits
MAX_MESSAGE_LENGTH = 4096
SAFE_MESSAGE_LENGTH = 4000  # Leave some room for emoji and formatting


def get_default_model_config() -> AgentModelConfig:
    """Get default model configuration (first model from OPENROUTER_MODELS)."""
    first_model = OPENROUTER_MODELS[0]
    return AgentModelConfig(
        provider=ModelProvider.OPENROUTER,
        model_id=first_model.id,
        temperature=0.7,
        max_tokens=None,  # Use model default
    )


def split_message(text: str, max_length: int = SAFE_MESSAGE_LENGTH) -> list[str]:
    """
    Split long message into chunks that fit Telegram limits.

    Tries to split on paragraph boundaries (\n\n), then line boundaries (\n),
    then word boundaries to preserve formatting.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Try to find a good split point
        split_point = max_length

        # Try paragraph boundary first
        last_para = remaining[:max_length].rfind("\n\n")
        if last_para > max_length // 2:  # At least half the chunk
            split_point = last_para + 2

        # Try line boundary
        elif (last_line := remaining[:max_length].rfind("\n")) > max_length // 2:
            split_point = last_line + 1

        # Try word boundary
        elif (last_space := remaining[:max_length].rfind(" ")) > max_length // 2:
            split_point = last_space + 1

        # Add chunk and continue
        chunks.append(remaining[:split_point].rstrip())
        remaining = remaining[split_point:].lstrip()

    return chunks


async def send_long_message(message: types.Message, text: str, prefix: str = "🤖") -> None:
    """
    Send a potentially long message, splitting or sending as file if needed.

    If message is short - send normally.
    If message is long but fits in multiple messages - split and send.
    If message is very long (>10 parts) - send as file.
    """
    full_text = f"{prefix} {text}" if prefix else text

    # Very long message - send as file
    if len(text) > SAFE_MESSAGE_LENGTH * 10:
        await message.answer("📄 Ответ слишком длинный, отправляю файлом:")
        file = BufferedInputFile(text.encode("utf-8"), filename="agent_response.txt")
        await message.answer_document(file, caption=f"{prefix} Ответ агента")
        return

    # Split and send multiple messages
    chunks = split_message(full_text)

    if len(chunks) == 1:
        # Single message - send normally
        await message.answer(full_text, parse_mode="HTML")
    else:
        # Multiple parts - send with part numbers
        for i, chunk in enumerate(chunks, 1):
            part_prefix = f"[{i}/{len(chunks)}] " if i > 1 else ""
            try:
                await message.answer(f"{part_prefix}{chunk}", parse_mode="HTML")
            except Exception:
                # If HTML parsing fails, send as plain text
                await message.answer(f"{part_prefix}{chunk}", parse_mode=None)


@router.message(Command("agent"), ChatTypeFilter("private"), SuperAdminFilter())
async def agent_command(message: types.Message, agent_service: AgentService) -> None:
    """
    Handle /agent command in private chat.

    Usage:
        /agent         - Show help
        /agent on      - Enable agent mode
        /agent off     - Disable agent mode
        /agent status  - Show current status
    """
    if not message.text:
        return

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []

    if not args or args[0] == "help":
        await message.answer(
            "🤖 <b>Агент-чат</b>\n\n"
            "<b>Команды:</b>\n"
            "/agent on - включить режим агента\n"
            "/agent off - выключить режим агента\n"
            "/agent status - показать статус\n\n"
            "<b>В режиме агента доступны только команды:</b>\n"
            "/new - начать новую сессию\n"
            "/agent status - показать статус\n"
            "/agent off - выйти из режима"
        )
        return

    if args[0] == "on":
        # Create new session and enable agent mode
        try:
            session = await agent_service.create_session(
                user_id=message.from_user.id,
                model_config=get_default_model_config(),
                title="Telegram Bot Private Chat",
            )
            _agent_mode_users[message.from_user.id] = session.id

            model_config = get_default_model_config()
            await message.answer(
                "✅ <b>Режим агента включен!</b>\n\n"
                f"🤖 Модель: {OPENROUTER_MODELS[0].name}\n"
                f"📝 Провайдер: {model_config.provider.value}\n\n"
                "Теперь я буду отвечать на все ваши сообщения как AI ассистент.\n\n"
                "<b>Доступные команды:</b>\n"
                "/new - начать новую сессию (очистить контекст)\n"
                "/agent status - показать статус сессии\n"
                "/agent off - выйти из режима агента"
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка при создании сессии: {e}")

    elif args[0] == "off":
        if message.from_user.id in _agent_mode_users:
            session_id = _agent_mode_users[message.from_user.id]
            del _agent_mode_users[message.from_user.id]
            await message.answer(
                "✅ <b>Режим агента выключен</b>\n\n"
                f"Сессия {session_id[:8]}... завершена.\n"
                "Обычный бот активен. Доступны все команды."
            )
        else:
            await message.answer("ℹ️ Режим агента не был включен.")

    elif args[0] == "status":
        if message.from_user.id in _agent_mode_users:
            session_id = _agent_mode_users[message.from_user.id]
            try:
                agent_session: AgentSession | None = await agent_service.get_session(session_id)
                if not agent_session:
                    await message.answer("⚠️ Сессия не найдена. Используйте /agent on для создания новой.")
                    return

                await message.answer(
                    "🤖 <b>Режим агента: ✅ Включен</b>\n\n"
                    f"📊 <b>Информация о сессии:</b>\n"
                    f"• ID: {session_id[:8]}...\n"
                    f"• Модель: {agent_session.agent_config.model_id}\n"
                    f"• Провайдер: {agent_session.agent_config.provider.value}\n"
                    f"• Сообщений: {len(agent_session.messages)}\n"
                    f"• Создана: {agent_session.created_at.strftime('%d.%m.%Y %H:%M')}"
                )
            except Exception as e:
                await message.answer(f"❌ Ошибка при получении статуса: {e}")
        else:
            await message.answer("🤖 <b>Режим агента: ❌ Выключен</b>\n\nИспользуйте /agent on для включения.")

    else:
        await message.answer(f"❌ Неизвестная команда: {args[0]}\n\nИспользуйте /agent для справки.")


@router.message(Command("new"), ChatTypeFilter("private"), SuperAdminFilter())
async def new_session_command(message: types.Message, agent_service: AgentService) -> None:
    """
    Create new agent session (clear context).

    Only available in agent mode.
    """
    user_id = message.from_user.id

    if user_id not in _agent_mode_users:
        await message.answer(
            "ℹ️ Команда /new доступна только в режиме агента.\n\nИспользуйте /agent on для включения режима агента."
        )
        return

    try:
        # Create new session
        session = await agent_service.create_session(
            user_id=user_id, model_config=get_default_model_config(), title="Telegram Bot Private Chat"
        )
        _agent_mode_users[user_id] = session.id

        await message.answer(
            "✅ <b>Новая сессия создана</b>\n\n"
            f"🆔 {session.id[:8]}...\n"
            f"🤖 Модель: {OPENROUTER_MODELS[0].name}\n\n"
            "Контекст очищен. Можете начать новый разговор."
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании новой сессии: {e}")


@router.message(
    F.text & ~F.text.startswith("/"),  # Only non-command text messages
    ChatTypeFilter("private"),
    SuperAdminFilter(),
)
async def agent_chat_handler(message: types.Message, agent_service: AgentService, bot: Bot) -> None:
    """
    Handle non-command text messages in agent mode with streaming.

    Streams agent responses in real-time, updating the message as text arrives.
    Only processes regular text messages (not commands) from super admins in private chat.
    Commands are handled by their respective handlers with higher priority.
    """
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id

    # Check if agent mode is enabled for this user
    if user_id not in _agent_mode_users:
        # Not in agent mode - ignore message (let other handlers process it)
        return

    session_id = _agent_mode_users[user_id]

    try:
        # Send typing indicator
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        # Send initial message that will be updated with streaming response
        response_msg = await message.answer("🤖 <i>Думаю...</i>", parse_mode="HTML")

        accumulated_text = ""
        last_update_time = time.time()
        update_interval = 0.5  # Update message every 0.5 seconds (Telegram rate limit)
        min_chars_for_update = 20  # Or when we have at least 20 new characters

        # Stream response from agent
        async for chunk in agent_service.chat_stream(session_id, message.text):
            accumulated_text = chunk
            current_time = time.time()

            # Update message if enough time has passed or we have significant new text
            should_update = (current_time - last_update_time >= update_interval) or (
                len(accumulated_text) - len(accumulated_text) >= min_chars_for_update
            )

            if should_update:
                try:
                    # Try to update with accumulated text
                    formatted_text = f"🤖 {accumulated_text}"

                    # If text is too long for single message, don't update - wait for final
                    if len(formatted_text) <= SAFE_MESSAGE_LENGTH:
                        await response_msg.edit_text(formatted_text, parse_mode="HTML")
                        last_update_time = current_time
                except Exception as e:
                    # If edit fails (e.g., message is identical or too similar), continue streaming
                    logger.debug(f"Failed to update message during streaming: {e}")

        # Final update with complete response
        # Use smart long message handler for final response
        with suppress(Exception):
            # Delete the "thinking" message (ignore errors if already deleted)
            await response_msg.delete()

        # Send final response (handles long messages)
        await send_long_message(message, accumulated_text, prefix="🤖")

    except ValueError as e:
        # Session not found - clear agent mode
        if user_id in _agent_mode_users:
            del _agent_mode_users[user_id]
        await message.answer(
            f"⚠️ Ошибка: {e}\n\nРежим агента был отключен. Используйте /agent on для создания новой сессии."
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке сообщения: {e}\n\nПопробуйте /new для новой сессии.")
