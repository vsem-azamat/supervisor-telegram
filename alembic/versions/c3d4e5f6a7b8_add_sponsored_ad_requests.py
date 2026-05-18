"""Add sponsored_ad_requests table.

Stores advertiser requests, accepted quote bounds, admin approval, and manual
payment confirmation for sponsored placements in managed chats.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sponsored_ad_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("target_chat_id", sa.BigInteger, nullable=False),
        sa.Column("advertiser_user_id", sa.BigInteger, nullable=False),
        sa.Column("source_message_id", sa.BigInteger, nullable=True),
        sa.Column("source_message_text", sa.String, nullable=True),
        sa.Column("content_text", sa.String, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("category_policy", sa.String(16), nullable=False, server_default="allowed"),
        sa.Column("wants_pin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("pin_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("quote_recommended_price", sa.Integer, nullable=True),
        sa.Column("quote_min_price", sa.Integer, nullable=True),
        sa.Column("quote_max_price", sa.Integer, nullable=True),
        sa.Column("final_price", sa.Integer, nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CZK"),
        sa.Column("admin_override", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("quote_provenance", sa.JSON, nullable=True),
        sa.Column("approved_by_admin_id", sa.BigInteger, nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("payment_confirmed_by_admin_id", sa.BigInteger, nullable=True),
        sa.Column("payment_confirmed_at", sa.DateTime, nullable=True),
        sa.Column("resolution_note", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sponsored_ad_requests_status", "sponsored_ad_requests", ["status"])
    op.create_index(
        "ix_sponsored_ad_requests_chat_status",
        "sponsored_ad_requests",
        ["target_chat_id", "status"],
    )
    op.create_index(
        "ix_sponsored_ad_requests_advertiser_created",
        "sponsored_ad_requests",
        ["advertiser_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sponsored_ad_requests_advertiser_created", table_name="sponsored_ad_requests")
    op.drop_index("ix_sponsored_ad_requests_chat_status", table_name="sponsored_ad_requests")
    op.drop_index("ix_sponsored_ad_requests_status", table_name="sponsored_ad_requests")
    op.drop_table("sponsored_ad_requests")
