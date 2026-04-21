"""Add chat_member_snapshots table.

Revision ID: f6a7b8c9d0e1
Revises: c663f6310e6f
Create Date: 2026-04-21 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "c663f6310e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_member_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("member_count", sa.Integer, nullable=False),
        sa.Column("captured_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_chat_member_snapshots_chat_id",
        "chat_member_snapshots",
        ["chat_id"],
    )
    op.create_index(
        "ix_chat_member_snapshots_captured_at",
        "chat_member_snapshots",
        ["captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_member_snapshots_captured_at", table_name="chat_member_snapshots")
    op.drop_index("ix_chat_member_snapshots_chat_id", table_name="chat_member_snapshots")
    op.drop_table("chat_member_snapshots")
