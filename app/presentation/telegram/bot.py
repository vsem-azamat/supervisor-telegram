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

    from app.channel.orchestrator import ChannelOrchestrator
    from app.telethon.telethon_client import TelethonClient
from app.db.session import close_db, create_session_maker, insert_chat_link
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
    """Main bot startup: webhook cleanup, chat links, Telethon."""
    try:
        from app.channel.cost_tracker import enable_persistence as enable_cost_persistence

        await bot.delete_webhook()
        await insert_chat_link()

        telethon_client = container.get_telethon_client()
        if telethon_client:
            await telethon_client.start()
            logger.info("telethon_started")

        enable_cost_persistence(True)
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

        from app.channel.llm_client import close_client as close_llm_client

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

    from app.presentation.telegram.handlers.channel_review import channel_review_router

    dp.include_router(channel_review_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return bot, dp


async def _resolve_channel_ids(
    bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Auto-resolve channel @usernames to numeric IDs via Bot API on startup."""
    from sqlalchemy import select, update

    from app.db.models import Channel, ChannelPost, ChannelSource

    async with session_maker() as session:
        result = await session.execute(select(Channel))
        channels = list(result.scalars().all())

    for channel in channels:
        # Skip if already a valid Telegram ID (large negative like -100XXXXXXXXXX)
        # Migration uses small negative placeholders (-1, -2, ...) = negative Channel.id
        if channel.telegram_id is not None and channel.telegram_id < -1000:
            continue

        username = channel.username
        if not username:
            logger.warning("channel_no_username_to_resolve", channel_id=channel.telegram_id)
            continue

        try:
            chat_info = await bot.get_chat(f"@{username.lstrip('@')}")
            numeric_id = chat_info.id
        except Exception:
            logger.exception("channel_resolve_failed", username=username)
            continue

        # The placeholder in child tables is the same as channel.telegram_id
        # (set by migration as -Channel.id). Use it for targeted UPDATE.
        old_id = channel.telegram_id
        async with session_maker() as session:
            await session.execute(update(Channel).where(Channel.id == channel.id).values(telegram_id=numeric_id))
            if old_id is not None:
                await session.execute(
                    update(ChannelPost).where(ChannelPost.channel_id == old_id).values(channel_id=numeric_id)
                )
                await session.execute(
                    update(ChannelSource).where(ChannelSource.channel_id == old_id).values(channel_id=numeric_id)
                )
            await session.commit()

        logger.info("channel_id_resolved", username=username, old_id=old_id, new_id=numeric_id)


def _init_channel_orchestrator(
    main_bot: Bot,
    session_maker: async_sessionmaker[AsyncSession],
) -> ChannelOrchestrator | None:
    """Initialize the channel content orchestrator if enabled."""
    try:
        config = settings.channel
        if config.enabled:
            from app.channel.orchestrator import ChannelOrchestrator

            orchestrator = ChannelOrchestrator(
                publish_bot=main_bot,
                config=config,
                api_key=settings.openrouter.api_key,
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
    if not settings.telethon.active:
        return None
    from app.telethon.telethon_client import TelethonClient

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

    # Validate: features requiring OpenRouter API key
    if settings.channel.enabled and not settings.openrouter.api_key:
        raise ValueError("CHANNEL_ENABLED=true requires OPENROUTER_API_KEY")

    session_maker = create_session_maker()

    # Phase 1: Initialize shared services
    # Registers itself in the container; nothing here needs the handle.
    _init_telethon()

    # Phase 2: The moderator bot — the only Telegram identity this process runs.
    main_bot, main_dp = _setup_main_bot(session_maker)
    setup_container(session_maker, main_bot)

    # Phase 2b: Auto-resolve channel telegram_ids via Bot API
    await _resolve_channel_ids(main_bot, session_maker)

    # Phase 3: Initialize channel orchestrator
    channel_orchestrator = _init_channel_orchestrator(main_bot, session_maker)
    if channel_orchestrator:
        container.set_channel_orchestrator(channel_orchestrator)

    # Phase 4: Run the polling loop and the background services
    polling_tasks = [
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

    polling_tasks.append(run_mcp_server())
    polling_tasks.append(run_expiry_sweep(session_maker))

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
