"""Shared E2E test fixtures."""

import pytest_asyncio
from app.infrastructure.db.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from tests.fake_telegram import FakeTelegramServer


@pytest_asyncio.fixture()
async def db_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session_maker(db_engine: AsyncEngine):
    """Async session maker bound to the in-memory engine."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture()
async def fake_tg():
    """Start fake Telegram server."""
    async with FakeTelegramServer() as server:
        yield server
