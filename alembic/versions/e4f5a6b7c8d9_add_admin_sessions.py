"""Add admin_sessions.

Opaque-token sessions for the web admin UI. session_id is a url-safe
random string (stored plaintext — it's already the secret, single-tenant
admin scope, no reason to hash). One row per active login.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-21 23:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False, index=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("admin_sessions")
