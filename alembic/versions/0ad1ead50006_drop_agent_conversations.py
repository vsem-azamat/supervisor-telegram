"""Drop agent conversations along with the assistant.

The table only ever backed the web UI's operator chat; the Telegram assistant
kept its history in memory. Both are gone.

Revision ID: 0ad1ead50006
Revises: 0ad1ead50005
Create Date: 2026-07-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50006"
down_revision: str | None = "0ad1ead50005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_agent_conversations_last_active_at", table_name="agent_conversations")
    op.drop_table("agent_conversations")


def downgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column("user_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_conversations_last_active_at", "agent_conversations", ["last_active_at"])
