"""Reconcile the adopted production database with the models.

The database this deployment runs on predates the migration squash: it was
stamped with the initial revision rather than built from it, and the two had
drifted in ways the squash could not know about. Nothing here is a schema
decision — each statement makes the models agree with what production already
held, or the other way round where production was right:

* five columns the models declare NOT NULL were nullable there. No row violates
  them (checked before writing this), so the constraint only writes down what is
  already true;
* two primary keys were bigint there and Integer in the models. Production was
  right — ``messages`` grows with every message the bot sees — so the models
  moved and this widens a database built from the squash.

Idempotent by nature: setting NOT NULL on a NOT NULL column and widening a
bigint to bigint are both no-ops, so this applies to either kind of database.

Revision ID: c8d5e2f47a19
Revises: a3f1c7d90b24
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8d5e2f47a19"
down_revision: Union[str, None] = "a3f1c7d90b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOT_NULL = [
    ("chats", "is_forum", sa.Boolean()),
    ("chats", "created_at", sa.DateTime()),
    ("chats", "modified_at", sa.DateTime()),
    ("users", "created_at", sa.DateTime()),
    ("users", "modified_at", sa.DateTime()),
]

_WIDENED = [("messages", "id"), ("chat_links", "id")]


def upgrade() -> None:
    for table, column, type_ in _NOT_NULL:
        op.alter_column(table, column, existing_type=type_, nullable=False)

    for table, column in _WIDENED:
        op.alter_column(table, column, existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    for table, column in _WIDENED:
        op.alter_column(table, column, existing_type=sa.BigInteger(), type_=sa.Integer())

    for table, column, type_ in _NOT_NULL:
        op.alter_column(table, column, existing_type=type_, nullable=True)
