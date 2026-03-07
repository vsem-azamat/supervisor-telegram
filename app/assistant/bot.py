"""Assistant bot — conversational interface for managing the Konnekt ecosystem.

Runs as a separate aiogram Bot + Dispatcher with its own middleware stack,
sharing the same DB session and channel orchestrator with the main moderation bot.
Uses PydanticAI agent with Claude Sonnet 4.6 via OpenRouter.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message  # noqa: TC002

from app.assistant.agent import AssistantDeps, create_assistant_agent
from app.assistant.config import AssistantSettings
from app.core.config import settings
from app.core.logging import get_logger
from app.core.markdown import md_to_entities_chunked

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.orchestrator import ChannelOrchestrator
    from app.infrastructure.telegram.telethon_client import TelethonClient

logger = get_logger("assistant.bot")

router = Router(name="assistant")

# Module-level references set during startup
_agent: Agent[AssistantDeps, str] | None = None
_deps: AssistantDeps | None = None
_super_admins: set[int] = set()

# Per-user conversation history with LRU eviction
_conversations: dict[int, list[ModelMessage]] = {}
_conversation_last_access: dict[int, float] = {}
_MAX_HISTORY = 40
_MAX_USERS = 50
_IDLE_TIMEOUT_SECONDS = 3600  # 1 hour

_AGENT_TIMEOUT_SECONDS = 120


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


async def _chat(user_id: int, user_message: str) -> str:
    """Send message to PydanticAI agent with conversation history."""
    if _agent is None or _deps is None:
        return "Агент не инициализирован."

    # Evict stale conversations before processing
    _evict_conversations()

    history = _conversations.get(user_id)

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

    # Track usage/cost
    from app.agent.channel.cost_tracker import extract_usage_from_pydanticai_result, log_usage

    usage = extract_usage_from_pydanticai_result(result, "anthropic/claude-sonnet-4-6", "assistant_chat")
    if usage:
        await log_usage(usage)

    # Save conversation for continuity
    all_msgs = list(result.all_messages())
    _conversations[user_id] = all_msgs
    _conversation_last_access[user_id] = time.monotonic()

    # Trim if too long — preserve the first message (initial ModelRequest) + last N-1
    if len(all_msgs) > _MAX_HISTORY:
        _conversations[user_id] = [all_msgs[0]] + all_msgs[-((_MAX_HISTORY) - 1) :]

    return result.output


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if message.from_user and message.from_user.id not in _super_admins:
        return

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
    if not message.from_user or message.from_user.id not in _super_admins:
        return
    if not message.text:
        return

    await message.bot.send_chat_action(message.chat.id, "typing")  # type: ignore[union-attr]

    try:
        response = await _chat(message.from_user.id, message.text)
    except Exception:
        logger.exception("assistant_chat_error", user_id=message.from_user.id)
        response = "Произошла ошибка. Попробуй ещё раз."

    # Convert Markdown → entities (no parse_mode needed)
    for chunk_text, chunk_entities in md_to_entities_chunked(response):
        await message.answer(chunk_text, entities=chunk_entities)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def setup_assistant(
    session_maker: async_sessionmaker[AsyncSession],
    main_bot: Bot,
    channel_orchestrator: ChannelOrchestrator | None = None,
    telethon_client: TelethonClient | None = None,
) -> tuple[Bot, Dispatcher] | None:
    """Create assistant Bot + Dispatcher. Returns None if disabled.

    Separated from polling so the main entry point can coordinate
    the lifecycle of all bots in one place.
    """
    global _agent, _deps, _super_admins  # noqa: PLW0603

    assistant_settings = AssistantSettings()
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
