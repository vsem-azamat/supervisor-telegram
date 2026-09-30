"""Who sees the feed, and in what order — without an HTTP client.

The feed is the second-largest algorithm in the product: a helper is shown
open requests ranked by how well they match what they actually offer. Both
halves of it are rules, not rendering, so both belong somewhere a test can
reach directly.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from students_cz.db.models import (
    Contact,
    HelperProfile,
    HelpRequest,
    Institution,
    Offer,
    ServiceType,
    Subject,
    User,
)
from students_cz.db.models.enums import (
    PublishStatus,
    RequestStatus,
    ResponseStatus,
    UiLang,
)
from students_cz.services import errors
from students_cz.services import requests as requests_service

pytestmark = pytest.mark.asyncio


async def _person(session: AsyncSession, tg_id: int) -> User:
    user = User(tg_id=tg_id, first_name="Marek", ui_lang=UiLang.RU)
    session.add(user)
    await session.flush()
    return user


async def _publisher(session: AsyncSession, tg_id: int) -> User:
    """A helper who is allowed to answer: published, and reachable."""
    user = await _person(session, tg_id)
    user.tg_username = f"helper{tg_id}"
    session.add(HelperProfile(user_id=user.id, status=PublishStatus.PUBLISHED))
    await session.flush()
    return user


async def _ask(session: AsyncSession, author: User, text: str, **extra) -> HelpRequest:
    request = HelpRequest(
        author_id=author.id,
        raw_text=text,
        status=RequestStatus.OPEN,
        langs=["ru"],
        **extra,
    )
    session.add(request)
    await session.flush()
    return request


async def test_somebody_with_no_helper_profile_is_refused(
    session: AsyncSession,
) -> None:
    user = await _person(session, 91201)
    with pytest.raises(errors.Forbidden):
        await requests_service.feed_for(session, user=user, limit=20)


async def test_a_draft_profile_may_look(session: AsyncSession) -> None:
    """Seeing that four people want your subject is the argument for finishing
    the profile; withholding it until published gets that backwards."""
    user = await _person(session, 91202)
    session.add(HelperProfile(user_id=user.id, status=PublishStatus.DRAFT))
    await session.flush()

    assert await requests_service.feed_for(session, user=user, limit=20) is not None


async def test_a_banned_profile_is_refused(session: AsyncSession) -> None:
    """The feed carries every author's name, photo, text and budget."""
    user = await _person(session, 91203)
    session.add(HelperProfile(user_id=user.id, status=PublishStatus.BANNED))
    await session.flush()

    with pytest.raises(errors.Forbidden):
        await requests_service.feed_for(session, user=user, limit=20)


async def test_your_own_requests_are_not_in_your_feed(session: AsyncSession) -> None:
    user = await _person(session, 91204)
    session.add(HelperProfile(user_id=user.id, status=PublishStatus.PUBLISHED))
    await session.flush()
    mine = await _ask(session, user, "мой собственный вопрос")

    rows = await requests_service.feed_for(session, user=user, limit=50)
    assert mine.id not in {row.request.id for row in rows}


async def test_a_closed_request_is_not_in_the_feed(session: AsyncSession) -> None:
    helper = await _person(session, 91205)
    session.add(HelperProfile(user_id=helper.id, status=PublishStatus.PUBLISHED))
    student = await _person(session, 91206)
    await session.flush()

    closed = await _ask(session, student, "уже не нужно")
    closed.status = RequestStatus.CLOSED
    await session.flush()

    rows = await requests_service.feed_for(session, user=helper, limit=50)
    assert closed.id not in {row.request.id for row in rows}


async def test_a_row_says_which_axes_it_matched(session: AsyncSession) -> None:
    """The reason line is rendered from these three flags, so they are the
    contract — not the sentence built out of them."""
    helper = await _person(session, 91207)
    session.add(HelperProfile(user_id=helper.id, status=PublishStatus.PUBLISHED))
    student = await _person(session, 91208)
    await session.flush()
    asked = await _ask(session, student, "нужен матан")

    rows = await requests_service.feed_for(session, user=helper, limit=50)
    [row] = [item for item in rows if item.request.id == asked.id]
    assert row.on_subject is False
    assert row.on_institution is False
    assert row.on_service is False
    assert row.author.id == student.id


async def test_a_request_on_your_subject_outranks_one_that_is_not(
    session: AsyncSession,
) -> None:
    """The ranking, not just the reason line.

    Both requests are open and answerable; the only difference is that one
    names a subject this helper offers. If the ORDER BY is lost, the two come
    back in insertion order and this fails — which is the point, because a
    silently reordered feed fails nothing else.
    """
    helper = await _person(session, 91209)
    student = await _person(session, 91210)
    session.add(HelperProfile(user_id=helper.id, status=PublishStatus.PUBLISHED))
    await session.flush()

    service_type_id = await session.scalar(
        select(ServiceType.id).where(ServiceType.code == "tutoring")
    )
    subject_id = await session.scalar(select(Subject.id).limit(1))
    assert service_type_id is not None and subject_id is not None

    session.add(
        Offer(
            helper_id=helper.id,
            service_type_id=service_type_id,
            subject_id=subject_id,
            is_active=True,
        )
    )

    # The matching one is written *first*, so every tiebreak works against it:
    # rows written in one transaction share created_at, and the id tiebreak is
    # descending. Only the ranking can lift it, which is what makes this a test
    # of the ranking rather than of insertion order.
    on_subject = await _ask(session, student, "мой предмет", subject_id=subject_id)
    unrelated = await _ask(session, student, "что-то другое")

    rows = await requests_service.feed_for(session, user=helper, limit=50)
    ordered = [
        row.request.id for row in rows if row.request.id in {unrelated.id, on_subject.id}
    ]

    assert ordered == [on_subject.id, unrelated.id]
    matched = next(row for row in rows if row.request.id == on_subject.id)
    assert matched.on_subject is True


async def test_your_own_faculty_counts_even_without_an_offer_for_it(
    session: AsyncSession,
) -> None:
    """A request from your own school is relevant whether or not you listed it."""
    institution_id = await session.scalar(select(Institution.id).limit(1))
    assert institution_id is not None

    helper = await _person(session, 91211)
    helper.institution_id = institution_id
    student = await _person(session, 91212)
    session.add(HelperProfile(user_id=helper.id, status=PublishStatus.PUBLISHED))
    await session.flush()

    asked = await _ask(session, student, "с факультета", institution_id=institution_id)

    rows = await requests_service.feed_for(session, user=helper, limit=50)
    [row] = [item for item in rows if item.request.id == asked.id]
    assert row.on_institution is True


# ── the lifecycle, without an HTTP client ───────────────────────────────


async def test_answering_needs_a_published_profile(session: AsyncSession) -> None:
    """A draft may look at the feed but not answer from it.

    An answer is an invitation to look at a profile, and a draft is not there
    to be looked at.
    """
    student = await _person(session, 91301)
    helper = await _person(session, 91302)
    helper.tg_username = "helper91302"
    session.add(HelperProfile(user_id=helper.id, status=PublishStatus.DRAFT))
    await session.flush()
    asked = await _ask(session, student, "матан")

    with pytest.raises(errors.Forbidden):
        await requests_service.respond(
            session, user=helper, request_id=asked.id, message="могу помочь"
        )


async def test_answering_needs_a_public_username(session: AsyncSession) -> None:
    """We do not host the conversation, so a handle is the only way back.

    Without one an accepted answer is a dead end: both sides told a deal
    happened, and neither able to reach the other.
    """
    student = await _person(session, 91303)
    helper = await _person(session, 91304)
    session.add(HelperProfile(user_id=helper.id, status=PublishStatus.PUBLISHED))
    await session.flush()
    asked = await _ask(session, student, "матан")

    with pytest.raises(errors.Conflict):
        await requests_service.respond(
            session, user=helper, request_id=asked.id, message="могу помочь"
        )


async def test_answering_the_same_request_twice_is_refused(
    session: AsyncSession,
) -> None:
    """Two taps on a slow connection are two concurrent inserts.

    The unique constraint would surface the second as a 500; this says what
    happened instead.
    """
    student = await _person(session, 91305)
    helper = await _publisher(session, 91306)
    asked = await _ask(session, student, "матан")

    await requests_service.respond(
        session, user=helper, request_id=asked.id, message="могу помочь"
    )
    with pytest.raises(errors.Conflict):
        await requests_service.respond(
            session, user=helper, request_id=asked.id, message="и ещё раз"
        )


async def test_answering_your_own_request_is_refused(session: AsyncSession) -> None:
    helper = await _publisher(session, 91307)
    mine = await _ask(session, helper, "сам себя")

    with pytest.raises(errors.BadRequest):
        await requests_service.respond(
            session, user=helper, request_id=mine.id, message="сам себе помогу"
        )


async def test_accepting_is_idempotent(session: AsyncSession) -> None:
    """A double tap must not write a second contact or send a second push.

    `contacts` has no unique index and should not have one — contacting the
    same person about two different requests is real.
    """
    student = await _person(session, 91308)
    helper = await _publisher(session, 91309)
    asked = await _ask(session, student, "матан")
    answered = await requests_service.respond(
        session, user=helper, request_id=asked.id, message="могу помочь"
    )

    first = await requests_service.accept(
        session, user=student, response_id=answered.response.id
    )
    second = await requests_service.accept(
        session, user=student, response_id=answered.response.id
    )

    assert first.notify is True
    assert second.notify is False, "the second acceptance told the helper again"

    contacts = await session.scalar(
        select(func.count()).select_from(Contact).where(Contact.request_id == asked.id)
    )
    assert contacts == 1


async def test_an_accepted_answer_cannot_be_declined(session: AsyncSession) -> None:
    """Otherwise the author reads "you declined" and the helper "you were
    chosen", with a recorded deal between them."""
    student = await _person(session, 91310)
    helper = await _publisher(session, 91311)
    asked = await _ask(session, student, "матан")
    answered = await requests_service.respond(
        session, user=helper, request_id=asked.id, message="могу помочь"
    )
    await requests_service.accept(session, user=student, response_id=answered.response.id)

    with pytest.raises(errors.Conflict):
        await requests_service.decline(
            session, user=student, response_id=answered.response.id
        )


async def test_somebody_else_s_response_reads_as_missing(session: AsyncSession) -> None:
    """404 rather than 403: whether an id exists is not a stranger's business."""
    student = await _person(session, 91312)
    helper = await _publisher(session, 91313)
    stranger = await _person(session, 91314)
    asked = await _ask(session, student, "матан")
    answered = await requests_service.respond(
        session, user=helper, request_id=asked.id, message="могу помочь"
    )

    with pytest.raises(errors.NotFound):
        await requests_service.accept(
            session, user=stranger, response_id=answered.response.id
        )


async def test_closing_someone_else_s_request_reads_as_missing(
    session: AsyncSession,
) -> None:
    student = await _person(session, 91315)
    stranger = await _person(session, 91316)
    asked = await _ask(session, student, "матан")

    with pytest.raises(errors.NotFound):
        await requests_service.close(session, user=stranger, request_id=asked.id)


async def test_answers_are_only_marked_read_once_the_author_has_them(
    session: AsyncSession,
) -> None:
    """Reading the list is what marks it, and only what was still unread.

    An accepted or declined answer must not be walked backwards to "read".
    """
    student = await _person(session, 91317)
    helper = await _publisher(session, 91318)
    asked = await _ask(session, student, "матан")
    await requests_service.respond(
        session, user=helper, request_id=asked.id, message="могу помочь"
    )

    rows = await requests_service.responses_for_author(
        session, user=student, request_id=asked.id
    )
    assert [row.status for row in rows] == [ResponseStatus.SENT]

    requests_service.mark_read(rows)
    again = await requests_service.responses_for_author(
        session, user=student, request_id=asked.id
    )
    assert [row.status for row in again] == [ResponseStatus.READ]


async def test_reading_the_answers_does_not_walk_a_decided_one_backwards(
    session: AsyncSession,
) -> None:
    """Only what is still unread changes.

    An accepted or declined answer has already been acted on; flipping it to
    "read" would lose that.
    """
    student = await _person(session, 91319)
    keen = await _publisher(session, 91320)
    other = await _publisher(session, 91321)
    asked = await _ask(session, student, "матан")

    chosen = await requests_service.respond(
        session, user=keen, request_id=asked.id, message="могу помочь"
    )
    await requests_service.respond(
        session, user=other, request_id=asked.id, message="я тоже могу"
    )
    await requests_service.accept(session, user=student, response_id=chosen.response.id)

    rows = await requests_service.responses_for_author(
        session, user=student, request_id=asked.id
    )
    requests_service.mark_read(rows)

    statuses = {
        row.helper_id: row.status
        for row in await requests_service.responses_for_author(
            session, user=student, request_id=asked.id
        )
    }
    assert statuses[keen.id] is ResponseStatus.ACCEPTED
    assert statuses[other.id] is ResponseStatus.READ


async def test_your_own_requests_are_capped(session: AsyncSession) -> None:
    """An unbounded list gets slower for exactly the heaviest users."""
    student = await _person(session, 91322)
    for index in range(requests_service.MY_REQUESTS_LIMIT + 3):
        await _ask(session, student, f"вопрос {index}")

    assert len(await requests_service.mine(session, user=student)) == (
        requests_service.MY_REQUESTS_LIMIT
    )
