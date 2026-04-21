"""Unit tests: Chat self-referencing parent/children relationship."""

from __future__ import annotations

import pytest
from app.db.models import Chat
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def test_chat_parent_and_children_navigate_both_directions(session) -> None:
    root = Chat(id=-100, title="ČVUT")
    child_a = Chat(id=-101, title="FEL", parent_chat_id=-100)
    child_b = Chat(id=-102, title="FIT", parent_chat_id=-100, relation_notes="faculty")
    session.add_all([root, child_a, child_b])
    await session.commit()

    fetched_root = (await session.execute(select(Chat).where(Chat.id == -100))).scalar_one()
    await session.refresh(fetched_root, ["children"])
    children_ids = sorted(c.id for c in fetched_root.children)
    assert children_ids == [-102, -101]

    fetched_child = (await session.execute(select(Chat).where(Chat.id == -101))).scalar_one()
    await session.refresh(fetched_child, ["parent"])
    assert fetched_child.parent is not None
    assert fetched_child.parent.id == -100
    assert fetched_child.parent.title == "ČVUT"


async def test_chat_relation_notes_persists(session) -> None:
    root = Chat(id=-200, title="Parent")
    child = Chat(id=-201, title="Child", parent_chat_id=-200, relation_notes="advertised by")
    session.add_all([root, child])
    await session.commit()

    fetched = (await session.execute(select(Chat).where(Chat.id == -201))).scalar_one()
    assert fetched.relation_notes == "advertised by"


async def test_chat_default_parent_chat_id_is_none(session) -> None:
    chat = Chat(id=-300, title="Standalone")
    session.add(chat)
    await session.commit()

    fetched = (await session.execute(select(Chat).where(Chat.id == -300))).scalar_one()
    assert fetched.parent_chat_id is None
    assert fetched.relation_notes is None
