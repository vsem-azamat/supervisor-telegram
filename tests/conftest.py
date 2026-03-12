import os
from collections.abc import AsyncGenerator
from typing import Any

# Setup test environment variables BEFORE any application imports
# This ensures configuration is available when modules are loaded
os.environ.update(
    {
        "DB_USER": "test",
        "DB_PASSWORD": "test",
        "DB_NAME": "test",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "BOT_TOKEN": "123456:ABC-DEF1234567890",
        "ADMIN_SUPER_ADMINS": "[123456789, 987654321]",  # JSON format for list
        "LOGGING_LEVEL": "ERROR",  # Reduce logging noise in tests
        "ENVIRONMENT": "test",
    }
)

import pytest
import pytest_asyncio
from app.domain.repositories import IAdminRepository, IChatRepository, IUserRepository
from app.infrastructure.db.base import Base
from app.infrastructure.db.repositories.admin import AdminRepository
from app.infrastructure.db.repositories.chat import ChatRepository
from app.infrastructure.db.repositories.user import UserRepository
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture(scope="function")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests with proper isolation."""
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        # Use nested transaction (savepoint) for test isolation
        # This allows repositories to commit while still maintaining isolation
        nested_transaction = await session.begin_nested()
        try:
            yield session
        finally:
            # Rollback the savepoint to undo all changes
            if nested_transaction.is_active:
                await nested_transaction.rollback()


@pytest_asyncio.fixture()
async def user_repository(session: AsyncSession) -> IUserRepository:
    """Create user repository for tests."""
    return UserRepository(session)


@pytest_asyncio.fixture()
async def chat_repository(session: AsyncSession) -> IChatRepository:
    """Create chat repository for tests."""
    return ChatRepository(session)


@pytest_asyncio.fixture()
async def admin_repository(session: AsyncSession) -> IAdminRepository:
    """Create admin repository for tests."""
    return AdminRepository(session)


@pytest.fixture
def sample_user_data() -> dict[str, Any]:
    """Sample user data for tests."""
    return {
        "id": 123456789,
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
    }


@pytest.fixture
def sample_chat_data() -> dict[str, Any]:
    """Sample chat data for tests."""
    return {
        "id": -1001234567890,
        "title": "Test Chat",
        "is_forum": False,
    }
