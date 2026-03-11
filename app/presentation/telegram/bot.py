"""Main entry point — starts all bots with coordinated lifecycle.

Architecture: each bot gets its own Dispatcher (independent middleware stacks),
but they share the same asyncio event loop, DB session maker, and Telethon client.
Both polling loops run concurrently via asyncio.gather().
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from app.core.config import settings
from app.core.container import container, setup_container
from app.core.logging import get_logger, setup_logging

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.channel.orchestrator import ChannelOrchestrator
    from app.infrastructure.telegram.telethon_client import TelethonClient
from app.infrastructure.db.session import close_db, create_session_maker, insert_chat_link
from app.presentation.telegram.handlers import router
from app.presentation.telegram.middlewares import (
    BlacklistMiddleware,
    DependenciesMiddleware,
    HistoryMiddleware,
    ManagedChatsMiddleware,
)

setup_logging()
logger = get_logger("bot")


# ---------------------------------------------------------------------------
# Lifecycle callbacks (main bot only)
# ---------------------------------------------------------------------------


async def on_startup(bot: Bot) -> None:
    """Main bot startup: webhook cleanup, chat links, Telethon."""
    try:
        await bot.delete_webhook()
        await insert_chat_link()

        telethon_client = container.get_telethon_client()
        if telethon_client:
            await telethon_client.start()
            logger.info("telethon_started")

        logger.info("main_bot_startup_complete")
    except Exception as e:
        logger.error("startup_error", error=str(e), exc_info=True)
        raise


async def on_shutdown(bot: Bot) -> None:
    """Main bot shutdown: orchestrator, Telethon, LLM client, DB (in dependency order)."""
    try:
        # Stop channel orchestrator first (it uses DB + LLM)
        orchestrator = container.get_channel_orchestrator()
        if orchestrator:
            await orchestrator.stop()

        telethon_client = container.get_telethon_client()
        if telethon_client:
            await telethon_client.stop()

        from app.agent.channel.llm_client import close_client as close_llm_client

        await close_llm_client()

        await bot.delete_webhook()
        await bot.close()
        await close_db()
        logger.info("main_bot_shutdown_complete")
    except Exception as e:
        logger.error("shutdown_error", error=str(e), exc_info=True)


# ---------------------------------------------------------------------------
# Initialization helpers
# ---------------------------------------------------------------------------


def _setup_main_bot(
    session_maker: async_sessionmaker[AsyncSession],
) -> tuple[Bot, Dispatcher]:
    """Create and configure the main moderation bot."""
    bot = Bot(token=settings.telegram.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    dp.update.middleware(DependenciesMiddleware(session_pool=session_maker, bot=bot))
    dp.update.middleware(ManagedChatsMiddleware())
    dp.update.middleware(HistoryMiddleware())
    dp.message.middleware(BlacklistMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return bot, dp


def _init_escalation_recovery(session_maker: async_sessionmaker[AsyncSession]) -> None:
    """Set up EscalationService session maker for timeout handlers."""
    if not (settings.agent.enabled and settings.agent.openrouter_api_key):
        logger.info("agent_disabled")
        return

    from app.agent.escalation import EscalationService

    EscalationService.set_session_maker(session_maker)
    logger.info("escalation_service_configured")


def _init_channel_orchestrator(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
) -> ChannelOrchestrator | None:
    """Initialize the channel content orchestrator if enabled."""
    try:
        config = settings.channel
        if config.enabled:
            from app.agent.channel.orchestrator import ChannelOrchestrator

            orchestrator = ChannelOrchestrator(
                bot=bot,
                config=config,
                api_key=settings.agent.openrouter_api_key,
                session_maker=session_maker,
            )
            orchestrator.start()
            logger.info("channel_agent_enabled")
            return orchestrator
    except Exception:
        logger.exception("channel_agent_init_failed")
    return None


def _init_telethon() -> TelethonClient | None:
    """Initialize Telethon client if configured."""
    if not settings.telethon.enabled:
        return None
    from app.infrastructure.telegram.telethon_client import TelethonClient

    client = TelethonClient(settings=settings.telethon)
    container.set_telethon_client(client)
    logger.info("telethon_configured", session=settings.telethon.session_name)
    return client


# ---------------------------------------------------------------------------
# Multi-bot polling coordinator
# ---------------------------------------------------------------------------


async def _run_polling(bot: Bot, dp: Dispatcher, *, name: str, **kwargs: Any) -> None:
    """Run a single bot's polling loop with structured logging."""
    logger.info("polling_start", bot=name)
    try:
        await dp.start_polling(bot, **kwargs)
    except asyncio.CancelledError:
        logger.info("polling_cancelled", bot=name)
    except Exception:
        logger.exception("polling_error", bot=name)
    finally:
        await bot.session.close()
        logger.info("polling_stopped", bot=name)


async def main() -> None:
    """Application entry point — coordinates all bots."""
    logger.info("starting", environment=settings.environment)

    session_maker = create_session_maker()

    # Phase 1: Initialize shared services
    _init_escalation_recovery(session_maker)
    if settings.agent.enabled and settings.agent.openrouter_api_key:
        from app.agent.escalation import EscalationService

        await EscalationService.recover_stale_escalations(session_maker)

    telethon_client = _init_telethon()

    # Phase 2: Setup main bot
    main_bot, main_dp = _setup_main_bot(session_maker)
    setup_container(session_maker, main_bot)

    channel_orchestrator = _init_channel_orchestrator(main_bot, session_maker)
    if channel_orchestrator:
        container.set_channel_orchestrator(channel_orchestrator)

    # Re-create main bot with orchestrator reference in DI middleware
    # (DependenciesMiddleware was already added, but orchestrator wasn't ready yet)
    # The middleware stores a reference to session_pool and bot, not orchestrator,
    # so this is fine. Orchestrator is accessed via container/direct reference.

    # Phase 3: Setup assistant bot (separate Dispatcher, no shared middleware)
    from app.assistant.bot import setup_assistant

    assistant_pair = setup_assistant(
        session_maker=session_maker,
        main_bot=main_bot,
        channel_orchestrator=channel_orchestrator,
        telethon_client=telethon_client,
    )

    # Phase 4: Run all polling loops concurrently
    polling_tasks = [
        _run_polling(
            main_bot,
            main_dp,
            name="main",
            skip_updates=True,
            allowed_updates=["message", "callback_query", "chat_member"],
        ),
    ]

    if assistant_pair:
        assistant_bot, assistant_dp = assistant_pair
        polling_tasks.append(
            _run_polling(
                assistant_bot,
                assistant_dp,
                name="assistant",
                skip_updates=True,
                allowed_updates=["message"],
                handle_signals=False,  # main bot handles SIGINT/SIGTERM
            ),
        )

    try:
        await asyncio.gather(*polling_tasks)
    finally:
        logger.info("all_bots_stopped")


def run_bot() -> None:
    """Run the bot."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("stopped_by_user")
    except Exception as e:
        logger.error("unexpected_error", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    run_bot()
