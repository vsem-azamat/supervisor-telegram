"""Channel telegram_id String to BigInteger.

Revision ID: c4d5e6f7a8b9
Revises: 1f95dc964397
Create Date: 2026-03-18 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "1f95dc964397"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables and columns to migrate
_TABLES = [
    ("channels", "telegram_id"),
    ("channel_posts", "channel_id"),
    ("channel_sources", "channel_id"),
]


def upgrade() -> None:
    # Phase 1: Convert @username strings to 0 (app startup will resolve via Bot API)
    for table, column in _TABLES:
        op.execute(
            sa.text(f"UPDATE {table} SET {column} = '0' WHERE {column} LIKE '@%'")  # noqa: S608
        )

    # Phase 2: Alter column type from String to BigInteger
    for table, column in _TABLES:
        op.alter_column(
            table,
            column,
            existing_type=sa.String(),
            type_=sa.BigInteger(),
            postgresql_using=f"{column}::bigint",
        )


def downgrade() -> None:
    for table, column in _TABLES:
        op.alter_column(
            table,
            column,
            existing_type=sa.BigInteger(),
            type_=sa.String(),
            postgresql_using=f"{column}::text",
        )
