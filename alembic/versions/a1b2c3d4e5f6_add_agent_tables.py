"""add agent_decisions and agent_escalations tables

Revision ID: a1b2c3d4e5f6
Revises: 73a429eaabbb
Create Date: 2026-03-02 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "73a429eaabbb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("reporter_id", sa.BigInteger(), nullable=True),
        sa.Column("message_text", sa.String(), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("admin_override", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_decisions_target_user_id", "agent_decisions", ["target_user_id"])
    op.create_index("ix_agent_decisions_chat_id", "agent_decisions", ["chat_id"])

    op.create_table(
        "agent_escalations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_text", sa.String(), nullable=True),
        sa.Column("suggested_action", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("admin_message_id", sa.BigInteger(), nullable=True),
        sa.Column("admin_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("resolved_action", sa.String(32), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("timeout_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_escalations_status", "agent_escalations", ["status"])


def downgrade() -> None:
    op.drop_table("agent_escalations")
    op.drop_table("agent_decisions")
