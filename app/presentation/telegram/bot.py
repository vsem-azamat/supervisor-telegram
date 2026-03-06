import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from app.core.config import settings
from app.core.container import container, setup_container
from app.core.logging import get_logger, setup_logging
from app.infrastructure.db.session import close_db, create_session_maker, insert_chat_link
from app.presentation.telegram.handlers import router
from app.presentation.telegram.middlewares import (
    BlacklistMiddleware,
    DependenciesMiddleware,
    HistoryMiddleware,
    ManagedChatsMiddleware,
)

# Setup logging
setup_logging()
logger = get_logger("bot")


async def on_startup(bot: Bot) -> None:
    """Bot startup handler."""
    try:
        await bot.delete_webhook()
        logger.info("Webhook deleted")

        await insert_chat_link()
        logger.info("Chat links initialized")

        # Start Telethon client if configured
        telethon_client = container.get_telethon_client()
        if telethon_client:
            await telethon_client.start()
            logger.info("Telethon client started")

        logger.info("Bot startup completed")
    except Exception as e:
        logger.error("Startup error", error=str(e), exc_info=True)
        raise


async def on_shutdown(bot: Bot) -> None:
    """Bot shutdown handler."""
    try:
        # Stop Telethon client
        telethon_client = container.get_telethon_client()
        if telethon_client:
            await telethon_client.stop()
            logger.info("Telethon client stopped")

        # Close the shared LLM httpx client
        from app.agent.channel.llm_client import close_client as close_llm_client

        await close_llm_client()
        logger.info("LLM client closed")

        await bot.delete_webhook()
        await bot.close()
        await close_db()
        logger.info("Bot shutdown completed")
    except Exception as e:
        logger.error("Shutdown error", error=str(e), exc_info=True)


async def get_bot_and_dp() -> tuple[Bot, Dispatcher]:
    """Create bot and dispatcher instances."""
    bot = Bot(token=settings.telegram.token, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    return bot, dp


async def main() -> None:
    """Main bot entry point."""
    logger.info("Starting bot", environment=settings.environment)

    # Create database session maker
    session_maker = create_session_maker()

    # Create bot and dispatcher
    bot, dp = await get_bot_and_dp()

    # Setup dependency injection
    setup_container(session_maker, bot)

    # Setup Telethon client if configured
    if settings.telethon.enabled:
        from app.infrastructure.telegram.telethon_client import TelethonClient

        telethon_client = TelethonClient(settings=settings.telethon)
        container.set_telethon_client(telethon_client)
        logger.info("Telethon client configured", session=settings.telethon.session_name)

    # Create agent (singleton, shared across requests) — lazy import to avoid circular deps
    agent_core = None
    if settings.agent.enabled and settings.agent.openrouter_api_key:
        from app.agent.core import AgentCore
        from app.agent.escalation import EscalationService

        agent_core = AgentCore()
        EscalationService.set_session_maker(session_maker)
        await EscalationService.recover_stale_escalations(session_maker)
        logger.info("Agent enabled", model=settings.agent.model)
    else:
        logger.info("Agent disabled (set AGENT_ENABLED=true and AGENT_OPENROUTER_API_KEY)")

    # Create channel content agent
    channel_orchestrator = None
    try:
        from app.agent.channel.config import ChannelAgentSettings

        channel_config = ChannelAgentSettings()
        if channel_config.enabled and (channel_config.channel_id or channel_config.channels):
            from app.agent.channel.orchestrator import ChannelOrchestrator

            channel_orchestrator = ChannelOrchestrator(
                bot=bot,
                config=channel_config,
                api_key=settings.agent.openrouter_api_key,
                session_maker=session_maker,
            )
            channel_orchestrator.start()
            logger.info(
                "Channel agent enabled",
                channel_id=channel_config.channel_id,
                sources=len(channel_config.rss_source_list),
            )
    except Exception:
        logger.exception("Channel agent init failed")

    # Setup middlewares
    dp.update.middleware(DependenciesMiddleware(session_pool=session_maker, bot=bot, agent_core=agent_core))
    dp.update.middleware(ManagedChatsMiddleware())
    dp.update.middleware(HistoryMiddleware())
    dp.message.middleware(BlacklistMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    # Start assistant bot as a background task.
    # NOTE: The assistant receives `bot` (main Bot instance) for Telegram API calls
    # (ban, mute, send_message). Both bots share the same aiohttp session, which is
    # safe since they run in the same asyncio event loop. The assistant creates its
    # own separate Bot instance for polling.
    assistant_task = None
    try:
        from app.assistant.bot import run_assistant_bot

        assistant_task = asyncio.create_task(
            run_assistant_bot(session_maker, bot, channel_orchestrator),
            name="assistant_bot",
        )
        logger.info("Assistant bot task created")
    except Exception:
        logger.exception("Assistant bot init failed")

    try:
        # Register handlers and lifecycle events
        dp.include_router(router)
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        logger.info("Bot configured, starting polling")
        await dp.start_polling(
            bot,
            skip_updates=True,
            allowed_updates=["message", "callback_query", "chat_member"],
        )

    except Exception as e:
        logger.error("Bot error", error=str(e), exc_info=True)
        raise

    finally:
        if assistant_task and not assistant_task.done():
            assistant_task.cancel()
        if channel_orchestrator:
            await channel_orchestrator.stop()
        await bot.session.close()
        logger.info("Bot session closed")


def run_bot() -> None:
    """Run the bot."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Unexpected error", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    run_bot()
