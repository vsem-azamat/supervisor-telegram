"""Add cost_events table.

Persistent log of LLM call costs. Written best-effort by cost_tracker.log_usage
when persistence is enabled at startup; queried by /api/costs/history for the
admin dashboard.

Revision ID: f7a8b9c0d1e2
Revises: e4f5a6b7c8d9
Create Date: 2026-04-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime, nullable=False, index=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False, index=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("cache_savings_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("channel_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cost_events")
