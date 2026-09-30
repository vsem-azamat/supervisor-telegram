"""Give subjects room for meaning

The third way of finding what somebody meant, after the synonym list and the
trigram: a vector per passage of a subject, so "объяснить пределы и производные"
can reach calculus without containing any of its names.

One row per passage rather than per subject — a subject is known by its name in
four languages and by its synonyms, and averaging those into one vector gives
something that is none of them. `model` is part of the key so a rollback finds
the vectors its own image made, and `text_sha` is what lets the rebuild skip
everything that has not changed.

No ANN index: twelve hundred rows scan faster than an index probes, and IVFFlat
built on this little data returns worse neighbours than none. See
docs/data-model.md.

Revision ID: 01b89b8f84b1
Revises: 4e1b96d7c8a2
Create Date: 2026-08-03

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "01b89b8f84b1"
down_revision: str | Sequence[str] | None = "4e1b96d7c8a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both paths create it — this one, and infra/postgres/init on a fresh
    # container — because either may be how a database comes into being.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "subject_embeddings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("subject_id", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("text_sha", sa.String(length=64), nullable=False),
        sa.Column(
            "embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_subject_embeddings_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject_embeddings")),
        sa.UniqueConstraint(
            "subject_id", "model", "text_sha", name="uq_subject_embeddings_source"
        ),
    )
    op.create_index(
        "ix_subject_embeddings_model", "subject_embeddings", ["model"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_subject_embeddings_model", table_name="subject_embeddings")
    op.drop_table("subject_embeddings")
    # The extension stays: dropping it would take any other table's vector
    # column with it, and nothing else here owns it.
