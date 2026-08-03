"""Give a chat somewhere for a stranger to join.

The public catalogue listed nine curated rows from `chat_links` while forty-five
chats existed, because `chats` had no link to offer. This is that link, and by
its presence the decision to publish: nullable, no default, so nothing becomes
public by running a migration.

Revision ID: f2c81a67e043
Revises: e7b3a48d0c15
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2c81a67e043"
down_revision: str | None = "e7b3a48d0c15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("public_link", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("chats", "public_link")
