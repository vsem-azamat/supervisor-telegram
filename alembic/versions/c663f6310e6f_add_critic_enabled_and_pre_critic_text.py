"""add critic_enabled and pre_critic_text

Revision ID: c663f6310e6f
Revises: 21c84750b5db
Create Date: 2026-04-17 21:17:44.955966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c663f6310e6f'
down_revision: Union[str, None] = '21c84750b5db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("critic_enabled", sa.Boolean(), nullable=True))
    op.add_column("channel_posts", sa.Column("pre_critic_text", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("channel_posts", "pre_critic_text")
    op.drop_column("channels", "critic_enabled")
