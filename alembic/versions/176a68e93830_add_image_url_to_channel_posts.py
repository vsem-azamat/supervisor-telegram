"""add image_url to channel_posts

Revision ID: 176a68e93830
Revises: 696e6c5e098a
Create Date: 2026-03-06 17:24:59.042170

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '176a68e93830'
down_revision: Union[str, None] = '696e6c5e098a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_posts', sa.Column('image_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('channel_posts', 'image_url')
