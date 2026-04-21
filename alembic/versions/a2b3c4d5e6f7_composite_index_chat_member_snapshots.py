"""Add composite index on chat_member_snapshots(chat_id, captured_at).

The detail-page query ``WHERE chat_id=? ORDER BY captured_at DESC LIMIT 50``
benefits from a composite seek+scan index. Drop the now-redundant single-column
chat_id index; the composite covers chat_id-only lookups too. Keep the
captured_at single-column index for the delta query (``WHERE captured_at >=
?`` without chat_id).

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-04-21 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_chat_member_snapshots_chat_id_captured_at",
        "chat_member_snapshots",
        ["chat_id", "captured_at"],
    )
    op.drop_index("ix_chat_member_snapshots_chat_id", table_name="chat_member_snapshots")


def downgrade() -> None:
    op.create_index(
        "ix_chat_member_snapshots_chat_id",
        "chat_member_snapshots",
        ["chat_id"],
    )
    op.drop_index(
        "ix_chat_member_snapshots_chat_id_captured_at",
        table_name="chat_member_snapshots",
    )
