"""add channels table, fix source uniqueness

Revision ID: 7323f6948691
Revises: a3b1c2d4e5f6
Create Date: 2026-03-07 07:55:57.308432

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7323f6948691"
down_revision: Union[str, None] = "a3b1c2d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create channels table
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="ru"),
        sa.Column("review_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("max_posts_per_day", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("posting_schedule", sa.JSON(), nullable=True),
        sa.Column("discovery_query", sa.String(), nullable=False, server_default=""),
        sa.Column("source_discovery_query", sa.String(), nullable=False, server_default=""),
        sa.Column("daily_posts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_count_date", sa.String(length=10), nullable=True),
        sa.Column("last_source_discovery_at", sa.DateTime(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_channels_telegram_id"), "channels", ["telegram_id"], unique=True)

    # 2. Fix channel_sources: drop global URL unique, add per-channel unique
    op.drop_constraint("channel_sources_url_key", "channel_sources", type_="unique")
    op.create_index(op.f("ix_channel_sources_url"), "channel_sources", ["url"], unique=False)
    op.create_unique_constraint("uq_channel_source_channel_url", "channel_sources", ["channel_id", "url"])

    # 3. Seed channels table from existing channel_posts/channel_sources data
    op.execute("""
        INSERT INTO channels (telegram_id, name, description, language)
        SELECT DISTINCT channel_id, channel_id, '', 'ru'
        FROM channel_posts
        WHERE channel_id NOT IN (SELECT telegram_id FROM channels)
        ON CONFLICT (telegram_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO channels (telegram_id, name, description, language)
        SELECT DISTINCT channel_id, channel_id, '', 'ru'
        FROM channel_sources
        WHERE channel_id NOT IN (SELECT telegram_id FROM channels)
        ON CONFLICT (telegram_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_constraint("uq_channel_source_channel_url", "channel_sources", type_="unique")
    op.drop_index(op.f("ix_channel_sources_url"), table_name="channel_sources")
    op.create_unique_constraint("channel_sources_url_key", "channel_sources", ["url"])
    op.drop_index(op.f("ix_channels_telegram_id"), table_name="channels")
    op.drop_table("channels")
