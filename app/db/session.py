from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("database")

# One engine per process, built on first use and reused from then on. The engine
# owns the connection pool, so a second one would mean a second pool competing
# for the same database — this is the thing that must not be per-caller.
engine: AsyncEngine | None = None
sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    """Create database engine."""
    return create_async_engine(
        settings.database.url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
    )


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """The process-wide session factory, built once.

    Callers ask for this freely — per update, per request, per MCP tool call —
    and get the same factory back; only the sessions it hands out are new. That
    is the intended shape: a session is a unit of work that borrows a connection
    from the pool for as long as it needs one and is not safe to share between
    concurrent tasks, so one per operation is correct. The engine underneath it
    is the shared, expensive part, and it is created here exactly once.
    """
    global engine, sessionmaker

    if not engine:
        engine = create_engine()

    if not sessionmaker:
        sessionmaker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    return sessionmaker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection."""
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    """Close database connections."""
    global engine
    if engine:
        await engine.dispose()
        engine = None
        logger.info("Database connections closed")


async def insert_chat_link() -> None:
    """Insert chat links from SQL script."""
    global engine
    if not engine:
        engine = create_engine()

    sql_script_path = "./scripts/insert_chat_links.sql"

    try:
        async with engine.begin() as conn:
            with Path(sql_script_path).open(encoding="utf-8") as file:
                for line_num, line in enumerate(file.readlines(), 1):
                    line = line.strip()
                    if line and not line.startswith("--"):
                        try:
                            await conn.execute(text(line))
                        except Exception as e:
                            logger.warning("Failed to execute SQL line", line_number=line_num, line=line, error=str(e))

        logger.info("Chat links inserted successfully")
    except FileNotFoundError:
        logger.warning(f"Chat links SQL file not found: {sql_script_path}")
    except Exception as e:
        logger.error("Failed to insert chat links", error=str(e), exc_info=True)
        raise
