import asyncio

from aiogram import Bot, Dispatcher
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from app.core.bot_factory import create_bot
from app.core.config import settings
from app.core.container import setup_container
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
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted")

        await insert_chat_link()
        logger.info("Chat links initialized")

        logger.info("Bot startup completed")
    except Exception as e:
        logger.error("Startup error", error=str(e), exc_info=True)
        raise


async def on_shutdown(bot: Bot) -> None:
    """Bot shutdown handler."""
    try:
        await bot.delete_webhook()
        await bot.close()
        await close_db()
        logger.info("Bot shutdown completed")
    except Exception as e:
        logger.error("Shutdown error", error=str(e), exc_info=True)


async def get_bot_and_dp() -> tuple[Bot, Dispatcher]:
    """Create bot and dispatcher instances."""
    bot = create_bot()
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

    # Setup middlewares
    dp.update.middleware(DependenciesMiddleware(session_pool=session_maker, bot=bot))
    dp.update.middleware(ManagedChatsMiddleware())
    dp.update.middleware(HistoryMiddleware())
    dp.message.middleware(BlacklistMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())

    try:
        # Register handlers and lifecycle events
        dp.include_router(router)
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)

        logger.info("Bot configured, starting polling")
        await dp.start_polling(bot)

    except Exception as e:
        logger.error("Bot error", error=str(e), exc_info=True)
        raise

    finally:
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
