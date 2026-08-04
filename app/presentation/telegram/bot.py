"""Main entry point — the moderator bot and the services beside it.

One Telegram identity, one dispatcher. Alongside its polling loop this process
also serves the MCP control plane and sweeps expired pending actions, because
both need what only this process holds: the Telethon session and the bot.
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

    from app.telethon.telethon_client import TelethonClient
from app.db.session import close_db, get_session_maker
from app.presentation.telegram.handlers import router
from app.presentation.telegram.middlewares import (
    ApprovedChatGateMiddleware,
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
    """Main bot startup: webhook cleanup and Telethon."""
    try:
        await bot.delete_webhook()

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
        telethon_client = container.get_telethon_client()
        if telethon_client:
            await telethon_client.stop()

        await bot.delete_webhook()
        await bot.close()
        await close_db()
        logger.info("main_bot_shutdown_complete")
    except Exception as e:
        logger.error("shutdown_error", error=str(e), exc_info=True)


# ---------------------------------------------------------------------------
# Initialization helpers
# ---------------------------------------------------------------------------


def _setup_main_bot(session_maker: async_sessionmaker[AsyncSession]) -> tuple[Bot, Dispatcher]:
    """Create and configure the moderation bot — the only bot in this process."""
    bot = Bot(token=settings.telegram.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    dp.update.middleware(DependenciesMiddleware(session_pool=session_maker, bot=bot))
    dp.update.middleware(ManagedChatsMiddleware())
    dp.update.middleware(HistoryMiddleware())
    dp.update.middleware(ApprovedChatGateMiddleware())
    dp.message.middleware(BlacklistMiddleware())
    # Also at the door: a blacklisted user who rejoins must not get to speak once first.
    dp.chat_member.middleware(BlacklistMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return bot, dp


def _init_telethon() -> TelethonClient | None:
    """Initialize Telethon client if configured."""
    if not settings.telethon.active:
        return None
    from app.telethon.telethon_client import TelethonClient

    client = TelethonClient(settings=settings.telethon)
    container.set_telethon_client(client)
    logger.info("telethon_configured", session=settings.telethon.session_name)
    return client


# ---------------------------------------------------------------------------
# Polling
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
    """Application entry point."""
    logger.info("starting", environment=settings.environment)

    session_maker = get_session_maker()

    # Registers itself in the container; only the MCP read tools ask for it,
    # and they say so plainly when it is absent.
    _init_telethon()

    main_bot, main_dp = _setup_main_bot(session_maker)
    setup_container(session_maker, main_bot)

    tasks = [
        _run_polling(
            main_bot,
            main_dp,
            name="main",
            skip_updates=True,
            allowed_updates=["message", "callback_query", "chat_member", "chat_join_request"],
        ),
    ]

    # The MCP control plane runs here, not in the web API: its tools need the
    # Telethon session and the confirmation handlers, and both belong to this
    # process. Returns immediately when MCP is inactive.
    from app.mcp.runner import run_mcp_server
    from app.moderation.pending_actions import run_expiry_sweep

    tasks.append(run_mcp_server())
    tasks.append(run_expiry_sweep(session_maker))

    # Member counts are recorded here because this is the process holding a
    # long-lived bot. Nothing about it is conditional any more: the loop asks
    # Telegram over the bot token, which every deployment has by definition.
    from app.chats.snapshots import run_snapshot_loop

    tasks.append(run_snapshot_loop(session_maker=session_maker, bot=main_bot))

    try:
        await asyncio.gather(*tasks)
    finally:
        logger.info("stopped")


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
