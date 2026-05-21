from app.sponsored_ads.leads import AdLeadRepository
from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_lead_defaults(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet="ad text")
    assert lead.id is not None
    assert lead.reached_via == "failed"
    assert lead.link_clicked_at is None


async def test_set_reached_via(session: AsyncSession) -> None:
    repo = AdLeadRepository(session)
    lead = await repo.create_lead(chat_id=-1001, user_id=7, snippet=None)
    await repo.set_reached_via(lead.id, "dm")
    refreshed = await repo.get_by_id(lead.id)
    assert refreshed is not None
    assert refreshed.reached_via == "dm"


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
