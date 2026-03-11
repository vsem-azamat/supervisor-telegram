"""add image_urls JSON to channel_posts

Revision ID: a3b1c2d4e5f6
Revises: 176a68e93830
Create Date: 2026-03-06 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3b1c2d4e5f6'
down_revision: Union[str, None] = '176a68e93830'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_posts', sa.Column('image_urls', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('channel_posts', 'image_urls')
