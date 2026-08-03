"""Give each administrator a list of the chats they may act in.

Until now `admins` was a flat list, so trusting somebody with one faculty chat
trusted them with the other forty-four. Nothing is migrated into the new table
because there is nothing to migrate: the production `admins` table is empty, and
guessing a scope for a row that does not exist would only invent authority.

Revision ID: e7b3a48d0c15
Revises: d4e9b1c26f83
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b3a48d0c15"
down_revision: str | None = "d4e9b1c26f83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_chats",
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("admin_id", "chat_id"),
    )


def downgrade() -> None:
    op.drop_table("admin_chats")
