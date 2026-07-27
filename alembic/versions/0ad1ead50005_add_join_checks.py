"""Add join checks awaiting a Mini App result.

Revision ID: 0ad1ead50005
Revises: 0ad1ead50004
Create Date: 2026-07-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50005"
down_revision: str | None = "0ad1ead50004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "join_checks",
        sa.Column("query_id", sa.String(length=128), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("passed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_join_checks_chat_id", "join_checks", ["chat_id"])
    op.create_index("ix_join_checks_user_id", "join_checks", ["user_id"])
    op.create_index("ix_join_checks_expires_at", "join_checks", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_join_checks_expires_at", table_name="join_checks")
    op.drop_index("ix_join_checks_user_id", table_name="join_checks")
    op.drop_index("ix_join_checks_chat_id", table_name="join_checks")
    op.drop_table("join_checks")
