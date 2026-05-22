from app.db.models import AdLead
from sqlalchemy.ext.asyncio import AsyncSession


async def test_ad_lead_persists_with_defaults(session: AsyncSession) -> None:
    lead = AdLead(chat_id=-1001, user_id=555, snippet="buy now cheap")
    session.add(lead)
    await session.flush()

    assert lead.id is not None
    assert lead.reached_via == "failed"
    assert lead.ping_chat_id is None
    assert lead.ping_message_id is None
    assert lead.created_at is not None
    assert lead.link_clicked_at is None
    assert lead.snippet == "buy now cheap"
