"""Add admin_magic_links.

Revision ID: b2c3d4e5f6a7
Revises: a8b9c0d1e2f3
Create Date: 2026-05-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_magic_links",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False, index=True),
        sa.Column("used_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("admin_magic_links")
