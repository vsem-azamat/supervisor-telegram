"""Add public ping message reference to ad_leads.

Revision ID: 0ad1ead50002
Revises: 0ad1ead50001
Create Date: 2026-05-22 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50002"
down_revision: str | None = "0ad1ead50001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ad_leads", sa.Column("ping_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("ad_leads", sa.Column("ping_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ad_leads", "ping_message_id")
    op.drop_column("ad_leads", "ping_chat_id")
