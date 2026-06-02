"""Add operating status to chats.

Revision ID: 0ad1ead50003
Revises: 0ad1ead50002
Create Date: 2026-06-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0ad1ead50003"
down_revision: str | None = "0ad1ead50002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column(
            "resource_status",
            sa.String(),
            nullable=False,
            server_default="approved",
        ),
    )
    op.create_check_constraint(
        "ck_chats_resource_status",
        "chats",
        "resource_status IN ('discovered', 'approved', 'disabled')",
    )
    op.alter_column("chats", "resource_status", server_default="discovered")


def downgrade() -> None:
    op.drop_constraint("ck_chats_resource_status", "chats", type_="check")
    op.drop_column("chats", "resource_status")
