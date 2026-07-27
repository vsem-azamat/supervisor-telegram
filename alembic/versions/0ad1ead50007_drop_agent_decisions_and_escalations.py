"""Drop the LLM moderation agent's tables.

Both were written only by the agent, whose single entry point left with the
conversational assistant. Nothing has been able to add a row since.

Revision ID: 0ad1ead50007
Revises: 0ad1ead50006
Create Date: 2026-07-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50007"
down_revision: str | None = "0ad1ead50006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("agent_escalations")
    op.drop_table("agent_decisions")

    # The action and origin columns are text; the enums that describe them live
    # in Python, so the database states them too rather than trusting callers.
    op.create_check_constraint(
        "ck_pending_actions_action", "pending_actions", "action IN ('ban', 'blacklist')"
    )
    op.create_check_constraint("ck_pending_actions_origin", "pending_actions", "origin IN ('mcp')")


def downgrade() -> None:
    op.drop_constraint("ck_pending_actions_origin", "pending_actions", type_="check")
    op.drop_constraint("ck_pending_actions_action", "pending_actions", type_="check")

    op.create_table(
        "agent_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("reporter_id", sa.BigInteger(), nullable=True),
        sa.Column("message_text", sa.String(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("admin_override", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "agent_escalations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.Integer(), nullable=True, index=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("message_text", sa.String(), nullable=True),
        sa.Column("suggested_action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("admin_message_id", sa.BigInteger(), nullable=True),
        sa.Column("admin_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolved_action", sa.String(length=32), nullable=True),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("timeout_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
