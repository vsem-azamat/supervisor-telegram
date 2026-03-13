"""Integration tests using testcontainers PostgreSQL.

Validates that repositories work correctly against a real PostgreSQL
database (not SQLite), catching dialect-specific issues.
"""

import pytest
from app.infrastructure.db.models import Admin, Chat, User
from app.infrastructure.db.repositories.admin import AdminRepository
from app.infrastructure.db.repositories.chat import ChatRepository
from app.infrastructure.db.repositories.user import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
class TestUserRepositoryPostgres:
    """User repository tests against real PostgreSQL."""

    async def test_save_and_get_user(self, pg_session: AsyncSession):
        repo = UserRepository(pg_session)
        user = User(
            id=111,
            username="testuser",
            first_name="Test",
            last_name="User",
        )
        saved = await repo.save(user)
        assert saved.id == 111
        assert saved.username == "testuser"

        retrieved = await repo.get_by_id(111)
        assert retrieved is not None
        assert retrieved.first_name == "Test"

    async def test_block_user(self, pg_session: AsyncSession):
        repo = UserRepository(pg_session)
        user = User(id=222, username="blockme", first_name="Block")
        await repo.save(user)
        await repo.add_to_blacklist(222)

        updated = await repo.get_by_id(222)
        assert updated is not None
        assert updated.is_blocked is True

    async def test_get_nonexistent_user(self, pg_session: AsyncSession):
        repo = UserRepository(pg_session)
        result = await repo.get_by_id(999999)
        assert result is None


@pytest.mark.integration
class TestChatRepositoryPostgres:
    """Chat repository tests against real PostgreSQL."""

    async def test_save_and_get_chat(self, pg_session: AsyncSession):
        repo = ChatRepository(pg_session)
        chat = Chat(
            id=-100123,
            title="Test Chat",
            welcome_message="Hello!",
        )
        saved = await repo.save(chat)
        assert saved.id == -100123

        retrieved = await repo.get_by_id(-100123)
        assert retrieved is not None
        assert retrieved.title == "Test Chat"


@pytest.mark.integration
class TestAdminRepositoryPostgres:
    """Admin repository tests against real PostgreSQL."""

    async def test_add_and_check_admin(self, pg_session: AsyncSession):
        repo = AdminRepository(pg_session)
        admin = Admin(id=333, state=True)
        await repo.save(admin)
        is_admin = await repo.is_admin(333)
        assert is_admin is True

    async def test_non_admin(self, pg_session: AsyncSession):
        repo = AdminRepository(pg_session)
        is_admin = await repo.is_admin(999)
        assert is_admin is False
