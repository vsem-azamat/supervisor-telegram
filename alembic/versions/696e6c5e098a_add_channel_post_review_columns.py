"""add channel post review columns and source relevance score

Revision ID: 696e6c5e098a
Revises: e3cd4fed09e2
Create Date: 2026-03-06 09:29:25.502656

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "696e6c5e098a"
down_revision: str | None = "e3cd4fed09e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("channel_posts", sa.Column("source_items", sa.JSON(), nullable=True))
    op.add_column("channel_posts", sa.Column("review_message_id", sa.BigInteger(), nullable=True))
    op.add_column("channel_posts", sa.Column("review_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("channel_posts", sa.Column("admin_feedback", sa.String(), nullable=True))
    # relevance_score was already included in the CREATE TABLE in e3cd4fed09e2;
    # this op.add_column would duplicate it on a fresh DB.  Skip it.


def downgrade() -> None:
    op.drop_column("channel_posts", "admin_feedback")
    op.drop_column("channel_posts", "review_chat_id")
    op.drop_column("channel_posts", "review_message_id")
    op.drop_column("channel_posts", "source_items")
