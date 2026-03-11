"""add scheduled post fields and publish_schedule

Revision ID: 36dc14a33db3
Revises: 930d376edcfd
Create Date: 2026-03-07 23:31:01.733738

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '36dc14a33db3'
down_revision: Union[str, None] = '930d376edcfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channel_posts', sa.Column('scheduled_at', sa.DateTime(), nullable=True))
    op.add_column('channel_posts', sa.Column('scheduled_telegram_id', sa.BigInteger(), nullable=True))
    op.add_column('channel_posts', sa.Column('published_at', sa.DateTime(), nullable=True))
    op.add_column('channels', sa.Column('publish_schedule', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('channels', 'publish_schedule')
    op.drop_column('channel_posts', 'published_at')
    op.drop_column('channel_posts', 'scheduled_telegram_id')
    op.drop_column('channel_posts', 'scheduled_at')
