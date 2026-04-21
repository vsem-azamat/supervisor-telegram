"""Add agent_conversations table.

One row per admin user, holds the serialized PydanticAI message history
so the /agent web chat can resume across reloads. JSON column stores the
output of `ModelMessagesTypeAdapter.dump_python(..., mode="json")`;
last_active_at supports idle eviction without scanning every row.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-21 23:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("user_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Index("ix_agent_conversations_last_active_at", "last_active_at"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_conversations_last_active_at", table_name="agent_conversations")
    op.drop_table("agent_conversations")
