"""Add moderation_events.

The bot kept no record of its own commands: a ``/ban`` typed in a chat left a
Telegram-side restriction and nothing else, so the only history a moderator
could read was of what the *user* had done.

Revision ID: a3f1c7d90b24
Revises: fbeb70328d81
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3f1c7d90b24"
down_revision: Union[str, None] = "fbeb70328d81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("target_user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "action IN ('ban', 'unban', 'kick', 'mute', 'unmute', 'blacklist', 'unblacklist')",
            name="ck_moderation_events_action",
        ),
        sa.CheckConstraint("source IN ('command', 'mcp')", name="ck_moderation_events_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_moderation_events_actor_id"), "moderation_events", ["actor_id"], unique=False)
    op.create_index(op.f("ix_moderation_events_chat_id"), "moderation_events", ["chat_id"], unique=False)
    op.create_index(
        op.f("ix_moderation_events_target_user_id"), "moderation_events", ["target_user_id"], unique=False
    )
    op.create_index(
        "ix_moderation_events_target_user_id_created_at",
        "moderation_events",
        ["target_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_events_target_user_id_created_at", table_name="moderation_events")
    op.drop_index(op.f("ix_moderation_events_target_user_id"), table_name="moderation_events")
    op.drop_index(op.f("ix_moderation_events_chat_id"), table_name="moderation_events")
    op.drop_index(op.f("ix_moderation_events_actor_id"), table_name="moderation_events")
    op.drop_table("moderation_events")
