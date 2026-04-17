"""add review_album_message_ids to channel_posts

Revision ID: 21c84750b5db
Revises: 3e8dba58c88d
Create Date: 2026-04-17 14:56:43.757137

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "21c84750b5db"
down_revision: str | None = "3e8dba58c88d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "channel_posts",
        sa.Column("review_album_message_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channel_posts", "review_album_message_ids")
