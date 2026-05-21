"""Add ad_leads table.

Tracks would-be advertisers redirected to the paid-placement rate card.

Revision ID: 0ad1ead50001
Revises: b2c3d4e5f6a7
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50001"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_leads",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("snippet", sa.String, nullable=True),
        sa.Column("reached_via", sa.String(8), nullable=False, server_default="failed"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("link_clicked_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_ad_leads_created_at", "ad_leads", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ad_leads_created_at", table_name="ad_leads")
    op.drop_table("ad_leads")
