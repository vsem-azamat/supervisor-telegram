"""add image_candidates and image_phashes to channel_posts

Revision ID: 3e8dba58c88d
Revises: d5e6f7a8b9c0
Create Date: 2026-04-17 11:14:01.944724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e8dba58c88d'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_posts', sa.Column('image_candidates', sa.JSON(), nullable=True))
    op.add_column('channel_posts', sa.Column('image_phashes', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('channel_posts', 'image_phashes')
    op.drop_column('channel_posts', 'image_candidates')
