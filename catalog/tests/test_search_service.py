"""What a sentence is understood to mean, and the two rows that records.

Reached without an HTTP client, which is the point: the parse writes — an
event and a `search_queries` row — and until this file those writes could only
be exercised through a signed request.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.db.models import SearchQuery, User, UserEvent
from students_cz.db.models.enums import UiLang, UserEventKind
from students_cz.services import search

pytestmark = pytest.mark.asyncio


async def _person(session: AsyncSession, tg_id: int) -> User:
    user = User(tg_id=tg_id, first_name="Sofia", ui_lang=UiLang.RU)
    session.add(user)
    await session.flush()
    return user


async def test_a_parse_is_logged_with_its_text_and_its_count(
    session: AsyncSession, helper_factory
) -> None:
    await helper_factory(tg_id=93101)
    viewer = await _person(session, 93102)

    out = await search.describe(
        session, UiLang.RU, viewer=viewer, text="матанализ репетитор"
    )

    assert out.matches >= 1
    row = await session.scalar(
        select(SearchQuery).where(SearchQuery.user_id == viewer.id)
    )
    assert row is not None
    assert row.raw_text == "матанализ репетитор"
    assert row.results_count == out.matches
    assert row.parsed["subject_id"] is not None
    events = await session.scalar(
        select(func.count())
        .select_from(UserEvent)
        .where(UserEvent.user_id == viewer.id, UserEvent.kind == UserEventKind.SEARCH)
    )
    assert events == 1


async def test_the_count_is_of_the_search_the_chips_describe(
    session: AsyncSession, helper_factory
) -> None:
    """Including the budget. A count that ignores a filter counts people the
    query does not reach, and writes that number into `search_queries`."""
    await helper_factory(tg_id=93103, price=900)
    viewer = await _person(session, 93104)

    out = await search.describe(
        session, UiLang.RU, viewer=viewer, text="матанализ до 300 крон"
    )

    assert out.matches == 0
    row = await session.scalar(
        select(SearchQuery).where(SearchQuery.user_id == viewer.id)
    )
    assert row is not None
    assert row.parsed["budget_max"] == 300


async def test_a_query_nobody_can_read_still_leaves_a_row(
    session: AsyncSession,
) -> None:
    """Those rows are the ranked list of what the catalog is missing."""
    viewer = await _person(session, 93105)

    out = await search.describe(session, UiLang.RU, viewer=viewer, text="ыфва цукен")

    assert out.chips == []
    assert out.note is not None
    row = await session.scalar(
        select(SearchQuery).where(SearchQuery.user_id == viewer.id)
    )
    assert row is not None
