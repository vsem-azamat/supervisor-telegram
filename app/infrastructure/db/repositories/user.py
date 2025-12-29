from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import UserEntity
from app.domain.exceptions import UserNotFoundException
from app.domain.repositories import IUserRepository
from app.infrastructure.db.models import User


class UserRepository(IUserRepository):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: int) -> UserEntity | None:
        result = await self.db.execute(select(User).filter(User.id == user_id))
        user_model = result.scalars().first()
        if not user_model:
            return None
        return self._model_to_entity(user_model)

    async def exists(self, user_id: int) -> bool:
        result = await self.db.execute(select(User.id).filter(User.id == user_id))
        return result.scalars().first() is not None

    async def save(self, user: UserEntity) -> UserEntity:
        user_model = await self._get_user_model(user.id)
        if user_model:
            user_model.username = user.username
            user_model.first_name = user.first_name
            user_model.last_name = user.last_name
            user_model.verify = user.is_verified
            user_model.blocked = user.is_blocked
        else:
            user_model = User(
                id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                verify=user.is_verified,
                blocked=user.is_blocked,
            )
            self.db.add(user_model)

        await self.db.commit()
        await self.db.refresh(user_model)
        return self._model_to_entity(user_model)

    async def get_blocked_users(self) -> list[UserEntity]:
        result = await self.db.execute(select(User).filter(User.blocked))
        user_models = result.scalars().all()
        return [self._model_to_entity(user_model) for user_model in user_models]

    async def find_blocked_user(self, identifier: str) -> UserEntity | None:
        """Find blocked user by username (without @) or user_id."""
        # Remove @ prefix if present
        if identifier.startswith("@"):
            identifier = identifier[1:]

        # Try to find by user_id if identifier is numeric
        if identifier.isdigit():
            user_id = int(identifier)
            result = await self.db.execute(select(User).filter(User.id == user_id, User.blocked))
        else:
            # Search by username
            result = await self.db.execute(select(User).filter(User.username == identifier, User.blocked))

        user_model = result.scalars().first()
        return self._model_to_entity(user_model) if user_model else None

    async def _get_user_model(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).filter(User.id == user_id))
        return result.scalars().first()

    def _model_to_entity(self, user_model: User) -> UserEntity:
        return UserEntity(
            id=user_model.id,
            username=user_model.username,
            first_name=user_model.first_name,
            last_name=user_model.last_name,
            is_verified=user_model.verify,
            is_blocked=user_model.blocked,
            created_at=user_model.created_at,
            modified_at=user_model.modified_at,
        )

    async def get_user(self, user_id: int) -> UserEntity | None:
        """Helper to get user entity by ID."""
        return await self.get_by_id(user_id)

    async def add_to_blacklist(self, user_id: int) -> None:
        user = await self.get_by_id(user_id)
        if user:
            await self.db.execute(update(User).where(User.id == user_id).values(blocked=True))
        else:
            await self.db.execute(insert(User).values(id=user_id, blocked=True))
        await self.db.commit()

    async def remove_from_blacklist(self, user_id: int) -> None:
        user = await self.get_by_id(user_id)
        if user:
            await self.db.execute(update(User).where(User.id == user_id).values(blocked=False))
            await self.db.commit()
        else:
            raise UserNotFoundException(user_id)


def get_user_repository(db: AsyncSession) -> "UserRepository":
    return UserRepository(db)
