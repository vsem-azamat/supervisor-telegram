from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Admin


class AdminRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, admin_id: int) -> Admin | None:
        """Get admin by ID."""
        result = await self.db.execute(select(Admin).filter(Admin.id == admin_id))
        return result.scalars().first()

    async def save(self, admin: Admin) -> Admin:
        """Save admin."""
        admin_model = await self._get_admin_model(admin.id)
        if admin_model:
            admin_model.state = admin.state
        else:
            admin_model = Admin(id=admin.id, state=admin.state)
            self.db.add(admin_model)

        await self.db.commit()
        await self.db.refresh(admin_model)
        return admin_model

    async def delete(self, admin_id: int) -> None:
        """Delete admin."""
        await self.db.execute(delete(Admin).where(Admin.id == admin_id))
        await self.db.commit()

    async def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        result = await self.db.execute(select(Admin).where(Admin.id == user_id).where(Admin.state))
        return result.scalars().first() is not None

    async def get_all_active(self) -> list[Admin]:
        """Get all active admins."""
        result = await self.db.execute(select(Admin).filter(Admin.state))
        return list(result.scalars().all())

    async def _get_admin_model(self, admin_id: int) -> Admin | None:
        """Get admin model by ID."""
        result = await self.db.execute(select(Admin).filter(Admin.id == admin_id))
        return result.scalars().first()

    # Legacy methods for backward compatibility
    async def get_db_admins(self) -> list[Admin]:
        """Get all admin models."""
        result = await self.db.execute(select(Admin))
        return list(result.scalars().all())

    async def insert_admin(self, id_tg: int) -> None:
        """Insert new admin (legacy method)."""
        await self.db.execute(insert(Admin).values(id=id_tg))
        await self.db.commit()

    async def delete_admin(self, id_tg: int) -> None:
        """Delete admin (legacy method)."""
        await self.delete(id_tg)


def get_admin_repository(db: AsyncSession) -> AdminRepository:
    return AdminRepository(db)
