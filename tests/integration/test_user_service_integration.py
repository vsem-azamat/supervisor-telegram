"""Integration tests for user management service workflows."""

import pytest
from app.application.services.user_service import UserService
from app.domain.entities import UserEntity
from app.domain.exceptions import UserNotFoundException
from app.domain.repositories import IUserRepository
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
class TestUserWorkflowIntegration:
    """Integration tests for complete user workflows."""

    async def test_complete_user_lifecycle(self, user_repository: IUserRepository, session: AsyncSession):
        """Test complete user lifecycle from creation to deletion."""
        user_service = UserService(user_repository)

        # 1. Create new user
        user_id = 123456789
        created_user = await user_service.create_or_update_user(
            user_id=user_id, username="testuser", first_name="Test", last_name="User"
        )

        assert created_user.id == user_id
        assert created_user.username == "testuser"
        assert created_user.is_blocked is False

        # 2. Verify user exists
        exists = await user_repository.exists(user_id)
        assert exists is True

        # 3. Update user profile
        updated_user = await user_service.create_or_update_user(
            user_id=user_id, username="updated_username", first_name="Updated", last_name="Name"
        )

        assert updated_user.username == "updated_username"
        assert updated_user.first_name == "Updated"

        # 4. Block user
        blocked_user = await user_service.block_user(user_id)
        assert blocked_user.is_blocked is True

        # 5. Verify user is in blocked list
        blocked_users = await user_service.get_blocked_users()
        assert len(blocked_users) >= 1
        assert any(user.id == user_id for user in blocked_users)

        # 6. Check blocked status
        is_blocked = await user_service.is_user_blocked(user_id)
        assert is_blocked is True

        # 7. Unblock user
        unblocked_user = await user_service.unblock_user(user_id)
        assert unblocked_user.is_blocked is False

        # 8. Verify user is not in blocked list anymore
        blocked_users_after = await user_service.get_blocked_users()
        assert not any(user.id == user_id for user in blocked_users_after)

        # 9. Final verification
        final_user = await user_service.get_user_by_id(user_id)
        assert final_user.username == "updated_username"
        assert final_user.is_blocked is False

    async def test_bulk_user_operations(self, user_repository: IUserRepository, session: AsyncSession):
        """Test bulk operations on multiple users."""
        user_service = UserService(user_repository)

        # Create multiple users
        user_ids = [100000001, 100000002, 100000003, 100000004, 100000005]
        created_users = []

        for i, user_id in enumerate(user_ids):
            user = await user_service.create_or_update_user(
                user_id=user_id, username=f"user{i}", first_name=f"User{i}", last_name=f"Test{i}"
            )
            created_users.append(user)

        # Verify all users were created
        assert len(created_users) == 5

        # Block some users
        for user_id in user_ids[:3]:  # Block first 3 users
            await user_service.block_user(user_id)

        # Verify blocked users
        blocked_users = await user_service.get_blocked_users()
        blocked_ids = {user.id for user in blocked_users}

        assert len(blocked_ids.intersection(set(user_ids[:3]))) == 3
        assert len(blocked_ids.intersection(set(user_ids[3:]))) == 0

        # Unblock all users
        for user_id in user_ids[:3]:
            await user_service.unblock_user(user_id)

        # Verify no users are blocked
        final_blocked_users = await user_service.get_blocked_users()
        final_blocked_ids = {user.id for user in final_blocked_users}

        assert len(final_blocked_ids.intersection(set(user_ids))) == 0

    async def test_user_edge_cases_workflow(self, user_repository: IUserRepository, session: AsyncSession):
        """Test edge cases in user workflow."""
        user_service = UserService(user_repository)

        # Test 1: Block non-existent user (should create and block)
        nonexistent_id = 999999999
        blocked_user = await user_service.block_user(nonexistent_id)

        assert blocked_user.id == nonexistent_id
        assert blocked_user.is_blocked is True

        # Test 2: Try to unblock user that's not blocked
        normal_user = await user_service.create_or_update_user(user_id=888888888, username="normal_user")

        # User is not blocked, so unblock should do nothing
        result = await user_service.unblock_user(normal_user.id)
        assert result.is_blocked is False

        # Test 3: Double block (should be idempotent)
        await user_service.block_user(normal_user.id)
        await user_service.block_user(normal_user.id)  # Second block

        final_user = await user_service.get_user_by_id(normal_user.id)
        assert final_user.is_blocked is True

        # Test 4: Block then immediately unblock
        test_user_id = 777777777
        await user_service.block_user(test_user_id)
        await user_service.unblock_user(test_user_id)

        final_test_user = await user_service.get_user_by_id(test_user_id)
        assert final_test_user.is_blocked is False

    async def test_concurrent_user_operations(self, user_repository: IUserRepository, session: AsyncSession):
        """Test concurrent operations on users."""

        user_service = UserService(user_repository)

        # Create users concurrently
        user_ids = list(range(200000001, 200000011))  # 10 users

        async def create_user(user_id: int) -> UserEntity:
            return await user_service.create_or_update_user(
                user_id=user_id, username=f"concurrent_user_{user_id}", first_name=f"User{user_id}"
            )

        # Create all users sequentially (SQLAlchemy session limitation)
        created_users = []
        for user_id in user_ids:
            user = await create_user(user_id)
            created_users.append(user)

        assert len(created_users) == 10
        assert all(user.username.startswith("concurrent_user_") for user in created_users)

        # Block users sequentially
        blocked_users = []
        for user_id in user_ids[:5]:
            user = await user_service.block_user(user_id)
            blocked_users.append(user)

        assert len(blocked_users) == 5
        assert all(user.is_blocked for user in blocked_users)

        # Verify final state
        all_blocked_users = await user_service.get_blocked_users()
        blocked_ids = {user.id for user in all_blocked_users}

        # Should contain at least our 5 blocked users
        assert len(blocked_ids.intersection(set(user_ids[:5]))) == 5

    async def test_user_profile_updates_workflow(self, user_repository: IUserRepository, session: AsyncSession):
        """Test various user profile update scenarios."""
        user_service = UserService(user_repository)
        user_id = 333333333

        # 1. Create user with minimal info
        user = await user_service.create_or_update_user(user_id=user_id, username="minimal_user")

        assert user.username == "minimal_user"
        assert user.first_name is None
        assert user.last_name is None

        # 2. Add first name
        user = await user_service.create_or_update_user(user_id=user_id, username="minimal_user", first_name="John")

        assert user.first_name == "John"
        assert user.last_name is None

        # 3. Add last name
        user = await user_service.create_or_update_user(
            user_id=user_id, username="minimal_user", first_name="John", last_name="Doe"
        )

        assert user.first_name == "John"
        assert user.last_name == "Doe"

        # 4. Update username
        user = await user_service.create_or_update_user(
            user_id=user_id, username="john_doe", first_name="John", last_name="Doe"
        )

        assert user.username == "john_doe"

        # 5. Clear some fields (set to None)
        user = await user_service.create_or_update_user(
            user_id=user_id, username=None, first_name="John", last_name=None
        )

        assert user.username is None
        assert user.first_name == "John"
        assert user.last_name is None

        # 6. Verify persistence
        retrieved_user = await user_service.get_user_by_id(user_id)
        assert retrieved_user.username is None
        assert retrieved_user.first_name == "John"
        assert retrieved_user.last_name is None


@pytest.mark.integration
class TestUserErrorScenariosIntegration:
    """Test error scenarios in user workflows."""

    async def test_nonexistent_user_operations(self, user_repository: IUserRepository, session: AsyncSession):
        """Test operations on non-existent users."""
        user_service = UserService(user_repository)
        nonexistent_id = 999999999

        # Test get_user_by_id with non-existent user
        with pytest.raises(UserNotFoundException) as exc_info:
            await user_service.get_user_by_id(nonexistent_id)

        assert exc_info.value.user_id == nonexistent_id

        # Test get_user_by_id_optional with non-existent user
        user = await user_service.get_user_by_id_optional(nonexistent_id)
        assert user is None

        # Test is_user_blocked with non-existent user
        is_blocked = await user_service.is_user_blocked(nonexistent_id)
        assert is_blocked is False

        # Test unblock non-existent user
        with pytest.raises(UserNotFoundException):
            await user_service.unblock_user(nonexistent_id)

    async def test_user_state_consistency(self, user_repository: IUserRepository, session: AsyncSession):
        """Test user state consistency across operations."""
        user_service = UserService(user_repository)
        user_id = 444444444

        # Create user
        user = await user_service.create_or_update_user(user_id=user_id, username="consistency_test")

        # Verify initial state
        assert user.is_blocked is False
        assert user.is_verified is True  # Default

        # Block user
        blocked_user = await user_service.block_user(user_id)
        assert blocked_user.is_blocked is True

        # Verify state persists across retrieval
        retrieved_user = await user_service.get_user_by_id(user_id)
        assert retrieved_user.is_blocked is True
        assert retrieved_user.is_verified is True  # Should remain unchanged

        # Update profile while blocked
        updated_user = await user_service.create_or_update_user(
            user_id=user_id, username="updated_username", first_name="Updated"
        )

        # Block status should persist
        assert updated_user.is_blocked is True
        assert updated_user.username == "updated_username"
        assert updated_user.first_name == "Updated"

        # Unblock user
        unblocked_user = await user_service.unblock_user(user_id)
        assert unblocked_user.is_blocked is False
        assert unblocked_user.username == "updated_username"  # Profile changes should persist
