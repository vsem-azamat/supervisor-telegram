"""Add spam_pings table.

Records ad-pattern hits (t.me / @username mentions) for the home
dashboard "Spam pings" tile and per-chat moderation feed. One row per
detection; the matched substrings are stored as a JSON list.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-21 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spam_pings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("matches", sa.JSON(), nullable=False),
        sa.Column("snippet", sa.String(), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Index("ix_spam_pings_chat_id_detected_at", "chat_id", "detected_at"),
        sa.Index("ix_spam_pings_detected_at", "detected_at"),
    )


def downgrade() -> None:
    op.drop_index("ix_spam_pings_detected_at", table_name="spam_pings")
    op.drop_index("ix_spam_pings_chat_id_detected_at", table_name="spam_pings")
    op.drop_table("spam_pings")
