"""Add chats.is_service_cleanup_enabled.

On by default, including for chats that already exist: a quiet chat reads as a
membership log otherwise, and every deployment of this bot has that problem
before it has any other.

Revision ID: d4e9b1c26f83
Revises: c8d5e2f47a19
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e9b1c26f83"
down_revision: str | None = "c8d5e2f47a19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("is_service_cleanup_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("chats", "is_service_cleanup_enabled")
