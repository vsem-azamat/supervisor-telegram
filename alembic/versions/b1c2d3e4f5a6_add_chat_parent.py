"""Add chat parent_chat_id + relation_notes.

Self-referencing FK lets us model the ČVUT → faculty → department tree
without a separate join table. Single column, nullable for roots.

Revision ID: b1c2d3e4f5a6
Revises: a2b3c4d5e6f7
Create Date: 2026-04-21 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column(
            "parent_chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chats.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("chats", sa.Column("relation_notes", sa.String(), nullable=True))
    op.create_index("ix_chats_parent_chat_id", "chats", ["parent_chat_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_parent_chat_id", table_name="chats")
    op.drop_column("chats", "relation_notes")
    op.drop_column("chats", "parent_chat_id")
