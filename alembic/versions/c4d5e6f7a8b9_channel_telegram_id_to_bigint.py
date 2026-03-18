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
    # Phase 1: Set non-numeric values (e.g. @username) to NULL
    for table, column in _TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET {column} = NULL "  # noqa: S608
                f"WHERE {column} !~ '^-?[0-9]+$'"
            )
        )

    # Phase 2: Drop unique constraint temporarily, alter type, re-add
    op.drop_index("ix_channels_telegram_id", table_name="channels")
    for table, column in _TABLES:
        op.alter_column(
            table,
            column,
            existing_type=sa.String(),
            type_=sa.BigInteger(),
            nullable=True,
            postgresql_using=f"{column}::bigint",
        )
    op.create_index("ix_channels_telegram_id", "channels", ["telegram_id"], unique=True)


def downgrade() -> None:
    for table, column in _TABLES:
        op.alter_column(
            table,
            column,
            existing_type=sa.BigInteger(),
            type_=sa.String(),
            postgresql_using=f"{column}::text",
        )
