"""FastAPI dependencies — DB session yielded from the shared async engine."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from app.db.session import create_session_maker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = create_session_maker()
    async with session_maker() as session:
        yield session
