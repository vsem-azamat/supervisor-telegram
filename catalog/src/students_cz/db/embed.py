"""Fill `subject_embeddings` from the catalog and the model.

Derived data: this is the only thing that writes the table, and it can be run
at any time without asking what state it is in. The deploy runs it after
`alembic upgrade head`, which is also what makes changing the model an ordinary
deploy — the new one writes its own rows under its own name, and the old ones
stay where they are so a rollback still finds vectors to search.

Cheap on every run but the first: a row is keyed by the passage's hash and the
model, so a catalog that has not changed has nothing to embed.
"""

import asyncio
import hashlib
import logging

from sqlalchemy import delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from students_cz.db.models import Subject, SubjectEmbedding
from students_cz.db.session import get_sessionmaker, unit_of_work
from students_cz.services.embedding import (
    MODEL_DIR,
    MODEL_NAME,
    Embedder,
    as_document,
    get_embedder,
)

log = logging.getLogger(__name__)


def passages(subject: Subject) -> list[str]:
    """Every way the catalog knows this subject, deduplicated.

    A leaf only: the tree's inner nodes are shelves rather than things anybody
    searches for, and embedding «Математика» would answer every maths query with
    the group instead of the subject.
    """
    texts = [name.name for name in subject.names if name.name]
    texts.extend(synonym for synonym in subject.synonyms if synonym.strip())
    return list(dict.fromkeys(texts))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def rebuild(session: AsyncSession, *, embedder: Embedder | None = None) -> int:
    """Bring the table in line with the catalog. Returns rows written."""
    model = embedder or get_embedder()
    if model is None:
        raise RuntimeError(
            f"no embedding model at {MODEL_DIR}: the rebuild is the one place "
            "that cannot do without it"
        )

    subjects = (
        await session.scalars(
            select(Subject)
            # Active leaves only, which is what `find_subjects` searches: a
            # subject withdrawn from the catalog must not stay reachable by
            # meaning after every other way to it has been closed.
            .where(Subject.kind == "leaf", Subject.is_active)
            .options(selectinload(Subject.names))
        )
    ).all()

    wanted: dict[tuple[int, str], str] = {}
    for subject in subjects:
        for text in passages(subject):
            wanted[(subject.id, sha(text))] = text

    # The two columns and not the rows: a thousand vectors of 768 floats each
    # would be read off the disk on every deploy to build a set of keys.
    have = {
        (subject_id, text_sha)
        for subject_id, text_sha in await session.execute(
            select(SubjectEmbedding.subject_id, SubjectEmbedding.text_sha).where(
                SubjectEmbedding.model == model.name
            )
        )
    }

    # Gone from the catalog: a synonym somebody removed must stop answering
    # queries, and only this notices — nothing else writes here.
    stale = have - set(wanted)
    if stale:
        await session.execute(
            delete(SubjectEmbedding).where(
                SubjectEmbedding.model == model.name,
                tuple_(SubjectEmbedding.subject_id, SubjectEmbedding.text_sha).in_(stale),
            )
        )

    missing = [(key, text) for key, text in wanted.items() if key not in have]
    if not missing:
        return 0

    vectors = model.encode([as_document(text) for _, text in missing])
    for ((subject_id, text_sha), text), vector in zip(missing, vectors, strict=True):
        session.add(
            SubjectEmbedding(
                subject_id=subject_id,
                model=model.name,
                source=text,
                text_sha=text_sha,
                embedding=vector,
            )
        )
    await session.flush()
    return len(missing)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with get_sessionmaker()() as session, unit_of_work(session) as scoped:
        written = await rebuild(scoped)
    log.info("subject embeddings: %d written, model %s", written, MODEL_NAME)


if __name__ == "__main__":
    asyncio.run(main())
