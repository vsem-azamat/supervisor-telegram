"""A category word is not a synonym of one member of it

`prijimacky` and `приймачки` sat in `subjects.synonyms` on «Поступление в
технические вузы», and a synonym scores 1.00 — so every «přijímačky …» query
came back filtered by maths and physics, including one that said medicine. The
word names a kind of help and reaches `entrance_prep` through the parser's
keyword table, which is where a category word belongs.

Here as well as in `seeds/subjects.json` because the deploy runs `alembic
upgrade head` and never the seed: production carries both synonyms today.

Revision ID: 4e1b96d7c8a2
Revises: c37f5a8e2b14
Create Date: 2026-08-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e1b96d7c8a2"
down_revision: str | Sequence[str] | None = "c37f5a8e2b14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SUBJECT = "prijimacky-technicke-vs"
WORDS = ("prijimacky", "приймачки")

# The other half of the same rule: the phrases people type for the medicine
# shelf, which the technical subject used to answer. Phrases and never the bare
# word — "медицина" belongs to the study group above.
MEDICINE = "prijimacky-medicina"
PHRASES = (
    "prijimacky na medicinu",
    "приймачки на медицину",
    "поступление на медицину",
    "vstup na medicinu",
)


# Declared under these two names so `tests/test_service_groups.py` can hold the
# seed and the migrations to the same synonyms: reference data lives in both
# places on purpose, and the pair drifting is invisible until a production query
# answers differently from every developer's.
SYNONYM_REMOVES: dict[str, tuple[str, ...]] = {SUBJECT: WORDS}
SYNONYM_ADDS: dict[str, tuple[str, ...]] = {MEDICINE: PHRASES}


def _add(bind, slug: str, words: tuple[str, ...]) -> None:
    for word in words:
        # Appended only when it is not already there, so running this against a
        # database somebody had already seeded does not leave the word twice.
        bind.execute(
            sa.text(
                "UPDATE subjects SET synonyms = synonyms || :word"
                " WHERE slug = :slug AND NOT (synonyms @> ARRAY[:word]::text[])"
            ),
            {"word": word, "slug": slug},
        )


def _remove(bind, slug: str, words: tuple[str, ...]) -> None:
    for word in words:
        bind.execute(
            sa.text(
                "UPDATE subjects SET synonyms = array_remove(synonyms, :word)"
                " WHERE slug = :slug"
            ),
            {"word": word, "slug": slug},
        )


def upgrade() -> None:
    bind = op.get_bind()
    for slug, words in SYNONYM_REMOVES.items():
        _remove(bind, slug, words)
    for slug, words in SYNONYM_ADDS.items():
        _add(bind, slug, words)


def downgrade() -> None:
    bind = op.get_bind()
    for slug, words in SYNONYM_ADDS.items():
        _remove(bind, slug, words)
    for slug, words in SYNONYM_REMOVES.items():
        _add(bind, slug, words)
