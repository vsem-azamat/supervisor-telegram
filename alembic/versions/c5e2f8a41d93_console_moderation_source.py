"""Moderation events may come from the console.

The console bans and unbans through the webapi, and those actions are now
recorded like the bot's commands and confirmed proposals.

The downgrade deletes the console's rows, since the narrower constraint cannot
hold them: who banned whom from the console is lost on the way back.

Revision ID: c5e2f8a41d93
Revises: b6d4a91c37e0
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c5e2f8a41d93"
down_revision: str | None = "b6d4a91c37e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_moderation_events_source", "moderation_events", type_="check")
    op.create_check_constraint(
        "ck_moderation_events_source", "moderation_events", "source IN ('command', 'mcp', 'console')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM moderation_events WHERE source = 'console'")
    op.drop_constraint("ck_moderation_events_source", "moderation_events", type_="check")
    op.create_check_constraint("ck_moderation_events_source", "moderation_events", "source IN ('command', 'mcp')")
