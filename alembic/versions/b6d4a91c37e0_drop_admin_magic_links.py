"""Take away the door that signed in without a password.

A magic link was a bearer token delivered through a chat: whoever held it was
the administrator, forwarding included. It existed because the console had no
way to know who was asking. A Mini App does — Telegram signs `initData` with
the bot's own token before the page loads — so the table has nothing left to
store.

It never stored anything in production either: not one row was ever written.
The downgrade recreates the shape rather than the contents, which is the most
a downgrade could honestly promise about single-use tokens.

Revision ID: b6d4a91c37e0
Revises: f2c81a67e043
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d4a91c37e0"
down_revision: str | None = "f2c81a67e043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The indexes go with it; Postgres drops a table's own indexes, and naming
    # them here would only be two more strings that could be wrong.
    op.drop_table("admin_magic_links")


def downgrade() -> None:
    op.create_table(
        "admin_magic_links",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_admin_magic_links_user_id", "admin_magic_links", ["user_id"])
    op.create_index("ix_admin_magic_links_expires_at", "admin_magic_links", ["expires_at"])
