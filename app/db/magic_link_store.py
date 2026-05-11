"""One-time magic links for web admin login.

The Telegram bot creates the token and only a SHA-256 digest is stored.
The web API consumes it exactly once and then creates a normal admin session.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
from typing import TYPE_CHECKING

from sqlalchemy import delete, update

from app.core.time import utc_now
from app.db.models import AdminMagicLink

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def new_magic_token() -> str:
    return secrets.token_urlsafe(32)


def hash_magic_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_magic_link(
    session: AsyncSession,
    *,
    user_id: int,
    ttl_minutes: int,
) -> tuple[str, AdminMagicLink]:
    now = utc_now()
    token = new_magic_token()
    row = AdminMagicLink(
        token_hash=hash_magic_token(token),
        user_id=user_id,
        created_at=now,
        expires_at=now + datetime.timedelta(minutes=ttl_minutes),
    )
    session.add(row)
    await session.commit()
    return token, row


async def consume_magic_link(session: AsyncSession, token: str) -> int | None:
    now = utc_now()
    result = await session.execute(
        update(AdminMagicLink)
        .where(
            AdminMagicLink.token_hash == hash_magic_token(token),
            AdminMagicLink.used_at.is_(None),
            AdminMagicLink.expires_at > now,
        )
        .values(used_at=now)
        .returning(AdminMagicLink.user_id)
    )
    user_id = result.scalar_one_or_none()
    await session.commit()
    return int(user_id) if user_id is not None else None


async def purge_expired(session: AsyncSession) -> int:
    now = utc_now()
    result = await session.execute(
        delete(AdminMagicLink).where(
            (AdminMagicLink.expires_at <= now) | (AdminMagicLink.used_at.is_not(None)),
        )
    )
    await session.commit()
    return result.rowcount or 0  # ty: ignore[unresolved-attribute]
