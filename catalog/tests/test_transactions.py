"""The request is one transaction, and it ends before the answer goes out.

The rule itself is exercised all over the suite — every test that writes and
reads back depends on it. What is tested here is the part that is easy to
break without noticing: *when* the transaction ends relative to the response.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import auth_header

pytestmark = pytest.mark.asyncio


async def test_a_failing_commit_is_not_answered_with_a_success(
    session: AsyncSession,
) -> None:
    """A commit that fails must reach the client as a failure.

    FastAPI tears a request-scoped `yield` dependency down *after* the response
    has been sent and after its background tasks have run. A session committed
    there would answer a success to a request whose write then failed, and
    would notify somebody about a row that never landed. `SessionDep` therefore
    asks for function scope; drop that argument and this test sees 200.
    """
    from students_cz.db.session import session_scope
    from students_cz.main import create_app

    async def failing_scope():
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            raise RuntimeError("commit blew up")

    app = create_app()
    app.dependency_overrides[session_scope] = failing_scope

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/api/v1/home", headers=auth_header(90777))

    assert response.status_code == 500, response.text
