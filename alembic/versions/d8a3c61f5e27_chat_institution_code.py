"""A chat names its university in teachers-catalog's taxonomy.

Nullable and unset for every existing chat: the console sets it on the chats
at the top, and the ones under them carry it through their parent.

Revision ID: d8a3c61f5e27
Revises: c5e2f8a41d93
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8a3c61f5e27"
down_revision: str | None = "c5e2f8a41d93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("institution_code", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("chats", "institution_code")
