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

_TABLES = [
    ("channels", "telegram_id"),
    ("channel_posts", "channel_id"),
    ("channel_sources", "channel_id"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Phase 1: Build mapping of @username -> Channel.id (PK) BEFORE nulling anything
    rows = conn.execute(
        sa.text("SELECT id, telegram_id FROM channels WHERE telegram_id !~ '^-?[0-9]+$'")
    ).fetchall()

    # Use negative Channel.id as unique placeholder per channel (e.g. -1, -2)
    # This avoids unique constraint violations and preserves channel identity
    mapping: dict[str, int] = {}  # old_string -> negative_pk
    for channel_pk, old_tid in rows:
        mapping[old_tid] = -channel_pk

    # Phase 2: Replace non-numeric strings with unique negative placeholders
    for old_tid, placeholder in mapping.items():
        conn.execute(
            sa.text("UPDATE channels SET telegram_id = :new WHERE telegram_id = :old"),
            {"new": str(placeholder), "old": old_tid},
        )
        # Update child tables: same old string -> same placeholder
        for table in ("channel_posts", "channel_sources"):
            conn.execute(
                sa.text(f"UPDATE {table} SET channel_id = :new WHERE channel_id = :old"),  # noqa: S608
                {"new": str(placeholder), "old": old_tid},
            )

    # Phase 3: Make all columns nullable, then ALTER TYPE
    for table, column in _TABLES:
        op.alter_column(table, column, existing_type=sa.String(), nullable=True)

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
    op.drop_index("ix_channels_telegram_id", table_name="channels")
    for table, column in _TABLES:
        op.alter_column(
            table,
            column,
            existing_type=sa.BigInteger(),
            type_=sa.String(),
            nullable=False,
            postgresql_using=f"COALESCE({column}::text, '')",
        )
    op.create_index("ix_channels_telegram_id", "channels", ["telegram_id"], unique=True)
