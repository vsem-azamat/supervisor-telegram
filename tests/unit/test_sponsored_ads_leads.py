from app.sponsored_ads.leads import AdLeadRepository
from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_lead_defaults(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet="ad text")
    assert lead.id is not None
    assert lead.reached_via == "failed"
    assert lead.ping_chat_id is None
    assert lead.ping_message_id is None
    assert lead.link_clicked_at is None


async def test_set_outreach_result(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet=None)
    await repo.set_outreach_result(lead.id, "ping", ping_chat_id=-1001, ping_message_id=55)
    refreshed = await repo.get_by_id(lead.id)
    assert refreshed is not None
    assert refreshed.reached_via == "ping"
    assert refreshed.ping_chat_id == -1001
    assert refreshed.ping_message_id == 55


async def test_mark_clicked_sets_timestamp_once(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet=None)

    assert await repo.mark_clicked(lead.id) is True
    first = await repo.get_by_id(lead.id)
    assert first is not None
    assert first.link_clicked_at is not None
    first_ts = first.link_clicked_at

    assert await repo.mark_clicked(lead.id) is True
    second = await repo.get_by_id(lead.id)
    assert second is not None
    assert second.link_clicked_at == first_ts  # not overwritten


async def test_mark_clicked_missing_lead(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    assert await repo.mark_clicked(999) is False


async def test_clear_ping_message(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet=None)
    await repo.set_outreach_result(lead.id, "ping", ping_chat_id=-1001, ping_message_id=55)

    await repo.clear_ping_message(lead.id)

    refreshed = await repo.get_by_id(lead.id)
    assert refreshed is not None
    assert refreshed.ping_chat_id is None
    assert refreshed.ping_message_id is None
