"""add channel_sources and channel_posts tables

Revision ID: e3cd4fed09e2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-06 08:49:34.828869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3cd4fed09e2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('channel_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('channel_id', sa.String(), nullable=False),
    sa.Column('url', sa.String(), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('language', sa.String(length=8), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('relevance_score', sa.Float(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('last_fetched_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.String(), nullable=True),
    sa.Column('added_by', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )
    op.create_index(op.f('ix_channel_sources_channel_id'), 'channel_sources', ['channel_id'], unique=False)

    op.create_table('channel_posts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('channel_id', sa.String(), nullable=False),
    sa.Column('external_id', sa.String(), nullable=False),
    sa.Column('source_url', sa.String(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('post_text', sa.String(), nullable=False),
    sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_channel_posts_channel_id'), 'channel_posts', ['channel_id'], unique=False)
    op.create_index(op.f('ix_channel_posts_external_id'), 'channel_posts', ['external_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_channel_posts_external_id'), table_name='channel_posts')
    op.drop_index(op.f('ix_channel_posts_channel_id'), table_name='channel_posts')
    op.drop_table('channel_posts')
    op.drop_index(op.f('ix_channel_sources_channel_id'), table_name='channel_sources')
    op.drop_table('channel_sources')
