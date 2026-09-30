"""The working-language list, cut from nine to four.

The list was wider than the interface, and the tail of it never matched a
single pair while making the question long enough to skip. Cutting it is easy;
the part worth a test is that nothing is deleted — `users.spoken_langs` and
`offers.langs` already hold these codes, and a row that vanished would take
somebody's profile data with it.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.db.models import Language
from students_cz.db.seed import WORKING_LANGUAGES, seed_languages

from .conftest import auth_header

pytestmark = pytest.mark.asyncio


async def test_four_languages_are_offered() -> None:
    assert [code for code, _ in WORKING_LANGUAGES] == ["ru", "uk", "cs", "en"]


async def test_the_endpoint_offers_exactly_those(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/taxonomy/languages", headers=auth_header())).json()

    assert [row["code"] for row in body] == ["ru", "uk", "cs", "en"]
    assert all(row["name"] for row in body)


async def _revive(session: AsyncSession, code: str) -> None:
    """Put a retired language back on its feet.

    Created or reactivated, depending on the database: a checkout seeded from
    scratch has never heard of Slovak, while one seeded before the cut still
    carries the row with `is_active` false. The test has to start from the
    same place either way.
    """
    row = await session.get(Language, code)
    if row is None:
        row = Language(code=code, sort=99)
        session.add(row)
    row.is_active = True
    await session.flush()


async def test_a_retired_language_is_deactivated_and_not_deleted(
    session: AsyncSession,
) -> None:
    """The row stays, so a profile that still claims Slovak keeps its data."""
    await _revive(session, "sk")

    await seed_languages(session)

    row = await session.get(Language, "sk")
    assert row is not None, "the row must survive — profiles reference the code"
    assert row.is_active is False


async def test_a_retired_language_disappears_from_the_endpoint(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _revive(session, "sk")
    await seed_languages(session)

    body = (await client.get("/api/v1/taxonomy/languages", headers=auth_header())).json()

    assert "sk" not in {row["code"] for row in body}
    still_there = await session.scalars(
        select(Language.code).where(Language.code == "sk")
    )
    assert still_there.all() == ["sk"]
