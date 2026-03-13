"""Assistant bot — conversational interface for managing the Konnekt ecosystem.

Runs as a separate aiogram Bot + Dispatcher with its own middleware stack,
sharing the same DB session and channel orchestrator with the main moderation bot.
Uses PydanticAI agent via OpenRouter with real-time streaming via sendMessageDraft.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.methods import SendMessageDraft
from aiogram.types import Message, MessageEntity, TelegramObject  # noqa: TC002

from app.agent.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage
from app.assistant.agent import AssistantDeps, create_assistant_agent
from app.core.config import settings
from app.core.logging import get_logger
from app.core.markdown import md_to_entities_chunked

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.orchestrator import ChannelOrchestrator
    from app.infrastructure.telegram.telethon_client import TelethonClient

logger = get_logger("assistant.bot")

router = Router(name="assistant")


class _SuperAdminOnlyMiddleware(BaseMiddleware):
    """Reject messages from non-super-admins with a polite reply."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and (not event.from_user or event.from_user.id not in _super_admins):
            await event.answer("Этот бот доступен только для администраторов.")
            return None
        return await handler(event, data)


router.message.middleware(_SuperAdminOnlyMiddleware())

# Module-level references set during startup
_agent: Agent[AssistantDeps, str] | None = None
_deps: AssistantDeps | None = None
_super_admins: set[int] = set()

# Per-user conversation history with LRU eviction
_conversations: dict[int, list[ModelMessage]] = {}
_conversation_last_access: dict[int, float] = {}
_conv_lock = asyncio.Lock()
_MAX_HISTORY = 40
_MAX_USERS = 50
_IDLE_TIMEOUT_SECONDS = 3600  # 1 hour

_AGENT_TIMEOUT_SECONDS = 180

# Streaming config
_STREAM_DEBOUNCE = 0.1  # seconds between stream_text yields
_DRAFT_MIN_INTERVAL = 0.3  # min seconds between sendMessageDraft calls
_DRAFT_MIN_CHARS = 20  # don't send draft until we have this many chars


def _evict_conversations() -> None:
    """Evict conversations idle for >1 hour, then enforce max user cap (LRU)."""
    now = time.monotonic()

    # 1. Evict idle conversations
    expired = [uid for uid, ts in _conversation_last_access.items() if now - ts > _IDLE_TIMEOUT_SECONDS]
    for uid in expired:
        _conversations.pop(uid, None)
        _conversation_last_access.pop(uid, None)

    # 2. Enforce max user cap — evict least recently used
    if len(_conversations) > _MAX_USERS:
        sorted_by_access = sorted(_conversation_last_access.items(), key=lambda x: x[1])
        to_remove = len(_conversations) - _MAX_USERS
        for uid, _ in sorted_by_access[:to_remove]:
            _conversations.pop(uid, None)
            _conversation_last_access.pop(uid, None)


async def _send_draft(
    bot: Bot,
    chat_id: int,
    draft_id: int,
    text: str,
    entities: list[MessageEntity] | None = None,
) -> None:
    """Send a streaming draft update to the user."""
    try:
        await bot(
            SendMessageDraft(
                chat_id=chat_id,
                draft_id=draft_id,
                text=text,
                entities=entities,
            )
        )
    except Exception:
        # Draft sending is best-effort — don't fail the whole response
        logger.debug("draft_send_failed", chat_id=chat_id)


async def _chat_stream(bot: Bot, chat_id: int, user_id: int, user_message: str) -> tuple[str, int]:
    """Stream agent response to user via sendMessageDraft, return (final_text, draft_id)."""
    if _agent is None or _deps is None:
        return "Агент не инициализирован.", 0

    async with _conv_lock:
        _evict_conversations()
        history = _conversations.get(user_id)
        # Trim history BEFORE sending to LLM to respect context window limits
        if history and len(history) > _MAX_HISTORY:
            from app.agent.tool_trace import trim_history

            history = trim_history(history, _MAX_HISTORY)
            _conversations[user_id] = history

    # Unique draft_id for this response (same id = animated updates)
    draft_id = random.randint(1, 2**31 - 1)  # noqa: S311
    last_draft_time = 0.0
    last_draft_text = ""

    try:
        async with asyncio.timeout(_AGENT_TIMEOUT_SECONDS):
            async with _agent.run_stream(
                user_message,
                deps=_deps,
                message_history=history,
            ) as stream_result:
                # Stream text chunks to user via drafts
                async for text_so_far in stream_result.stream_text(debounce_by=_STREAM_DEBOUNCE):
                    now = time.monotonic()
                    # Throttle: only send draft if enough time passed and text changed meaningfully
                    if (
                        len(text_so_far) >= _DRAFT_MIN_CHARS
                        and now - last_draft_time >= _DRAFT_MIN_INTERVAL
                        and text_so_far != last_draft_text
                    ):
                        # Truncate to 4096 for draft (Telegram limit)
                        draft_text = text_so_far[:4096]
                        await _send_draft(bot, chat_id, draft_id, draft_text + " ▍")
                        last_draft_time = now
                        last_draft_text = text_so_far

                # Get final output
                final_output = await stream_result.get_output()

                # Send final draft without cursor — smooths transition to sendMessage
                plain_preview = final_output[:4096]
                if plain_preview != last_draft_text:
                    await _send_draft(bot, chat_id, draft_id, plain_preview)

                # Track usage/cost
                usage = extract_usage_from_pydanticai_result(stream_result, settings.assistant.model, "assistant_chat")
                if usage:
                    await log_usage(usage)

                # Save conversation
                all_msgs = list(stream_result.all_messages())
                async with _conv_lock:
                    _conversations[user_id] = all_msgs
                    _conversation_last_access[user_id] = time.monotonic()

                # Prepend tool call trace so the user sees what happened
                from app.agent.tool_trace import format_response_with_trace

                new_msgs = list(stream_result.new_messages())
                final_output = format_response_with_trace(new_msgs, final_output)

                return final_output, draft_id

    except TimeoutError:
        logger.warning("assistant_agent_timeout", user_id=user_id, timeout=_AGENT_TIMEOUT_SECONDS)
        return "Превышено время ожидания ответа от агента. Попробуй ещё раз или упрости запрос.", draft_id


async def _chat(user_id: int, user_message: str) -> str:
    """Non-streaming fallback — send message to PydanticAI agent with conversation history."""
    if _agent is None or _deps is None:
        return "Агент не инициализирован."

    async with _conv_lock:
        _evict_conversations()
        history = _conversations.get(user_id)
        if history and len(history) > _MAX_HISTORY:
            from app.agent.tool_trace import trim_history

            history = trim_history(history, _MAX_HISTORY)
            _conversations[user_id] = history

    try:
        result = await asyncio.wait_for(
            _agent.run(
                user_message,
                deps=_deps,
                message_history=history,
            ),
            timeout=_AGENT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("assistant_agent_timeout", user_id=user_id, timeout=_AGENT_TIMEOUT_SECONDS)
        return "Превышено время ожидания ответа от агента. Попробуй ещё раз или упрости запрос."

    usage = extract_usage_from_pydanticai_result(result, settings.assistant.model, "assistant_chat")
    if usage:
        await log_usage(usage)

    all_msgs = list(result.all_messages())
    async with _conv_lock:
        _conversations[user_id] = all_msgs
        _conversation_last_access[user_id] = time.monotonic()

    from app.agent.tool_trace import format_response_with_trace

    new_msgs = list(result.new_messages())
    return format_response_with_trace(new_msgs, result.output)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я Konnekt Assistant — управляю всей экосистемой.\n\n"
        "Я могу:\n"
        "- Управлять каналами и контент-пайплайном\n"
        "- Модерировать чаты (мут, бан, разбан)\n"
        "- Управлять чёрным списком\n"
        "- Отправлять сообщения в любой чат/канал\n"
        "- Настраивать приветственные сообщения\n"
        "- Показывать статистику и расходы\n\n"
        "Просто напиши что нужно — я пойму.",
    )


@router.message(F.text)
async def handle_message(message: Message) -> None:
    if not message.from_user or not message.text or not message.bot:
        return

    bot = message.bot
    chat_id = message.chat.id
    draft_id = 0

    try:
        response, draft_id = await _chat_stream(bot, chat_id, message.from_user.id, message.text)
    except Exception:
        logger.exception("assistant_chat_error", user_id=message.from_user.id)
        response = "Произошла ошибка. Попробуй ещё раз."

    # Convert markdown → plain text + entities, split into Telegram-safe chunks
    chunks = md_to_entities_chunked(response)

    # Send final message — auto-clears any active draft with the same chat_id
    for chunk_text, chunk_entities in chunks:
        await message.answer(chunk_text, entities=chunk_entities, parse_mode=None)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def setup_assistant(
    session_maker: async_sessionmaker[AsyncSession],
    main_bot: Bot,
    channel_orchestrator: ChannelOrchestrator | None = None,
    telethon_client: TelethonClient | None = None,
) -> tuple[Bot, Dispatcher] | None:
    """Create assistant Bot + Dispatcher. Returns None if disabled."""
    global _agent, _deps, _super_admins  # noqa: PLW0603

    assistant_settings = settings.assistant
    if not assistant_settings.enabled or not assistant_settings.token:
        logger.info("assistant_bot_disabled")
        return None

    _agent = create_assistant_agent()
    _deps = AssistantDeps(
        session_maker=session_maker,
        main_bot=main_bot,
        channel_orchestrator=channel_orchestrator,
        telethon=telethon_client,
    )
    _super_admins = set(settings.admin.super_admins)

    bot = Bot(token=assistant_settings.token)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("assistant_bot_setup", admins=len(_super_admins))
    return bot, dp
