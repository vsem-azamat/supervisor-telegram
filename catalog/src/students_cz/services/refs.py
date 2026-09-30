"""Existence checks for the taxonomy a request refers to by id."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.services.errors import Invalid


async def require_row(
    session: AsyncSession, model, value: int | None, field: str
) -> None:
    """Reject an unknown foreign key here rather than at the database.

    Without this a typo'd id surfaces as ForeignKeyViolation — a 500 that says
    nothing useful — instead of a 422 naming the field.
    """
    if value is None:
        return
    if await session.scalar(select(model.id).where(model.id == value)) is None:
        raise Invalid(f"unknown {field}: {value}")
