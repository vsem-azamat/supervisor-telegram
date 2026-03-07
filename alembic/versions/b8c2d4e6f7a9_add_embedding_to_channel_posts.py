"""add embedding vector to channel_posts

Revision ID: b8c2d4e6f7a9
Revises: 7323f6948691
Create Date: 2026-03-07 14:00:00.000000

"""

from typing import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c2d4e6f7a9"
down_revision: str | None = "7323f6948691"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add embedding column (768-dim vector) and model name directly as vector type
    op.execute("ALTER TABLE channel_posts ADD COLUMN embedding vector(768)")
    op.execute("ALTER TABLE channel_posts ADD COLUMN embedding_model varchar(64)")

    # Add unique constraint on (channel_id, external_id) to prevent race condition dupes
    op.create_unique_constraint("uq_channel_post_channel_external", "channel_posts", ["channel_id", "external_id"])

    # Create HNSW index for fast cosine similarity search
    op.execute(
        "CREATE INDEX ix_channel_posts_embedding ON channel_posts "
        "USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_channel_posts_embedding")
    op.drop_constraint("uq_channel_post_channel_external", "channel_posts", type_="unique")
    op.execute("ALTER TABLE channel_posts DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE channel_posts DROP COLUMN IF EXISTS embedding")
