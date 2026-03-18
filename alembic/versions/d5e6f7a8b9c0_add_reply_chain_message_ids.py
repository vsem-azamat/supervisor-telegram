"""Add reply_chain_message_ids to channel_posts.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-03-18 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("channel_posts", sa.Column("reply_chain_message_ids", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("channel_posts", "reply_chain_message_ids")
