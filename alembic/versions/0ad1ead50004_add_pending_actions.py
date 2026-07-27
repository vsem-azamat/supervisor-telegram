"""Add pending actions awaiting admin confirmation.

Revision ID: 0ad1ead50004
Revises: 0ad1ead50003
Create Date: 2026-07-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50004"
down_revision: str | None = "0ad1ead50003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("initiator_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("admin_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("admin_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_check_constraint(
        "ck_pending_actions_status",
        "pending_actions",
        "status IN ('pending', 'confirmed', 'rejected', 'expired')",
    )
    op.create_index("ix_pending_actions_initiator_id", "pending_actions", ["initiator_id"])
    op.create_index("ix_pending_actions_chat_id", "pending_actions", ["chat_id"])
    op.create_index("ix_pending_actions_target_user_id", "pending_actions", ["target_user_id"])
    # Sweeping for things to expire always filters on both columns together.
    op.create_index("ix_pending_actions_status_expires_at", "pending_actions", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_pending_actions_status_expires_at", table_name="pending_actions")
    op.drop_index("ix_pending_actions_target_user_id", table_name="pending_actions")
    op.drop_index("ix_pending_actions_chat_id", table_name="pending_actions")
    op.drop_index("ix_pending_actions_initiator_id", table_name="pending_actions")
    op.drop_constraint("ck_pending_actions_status", "pending_actions", type_="check")
    op.drop_table("pending_actions")
