# Phase 4a — Auth Foundation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the dev no-op `require_super_admin` with a real session-cookie flow: Telegram Login Widget → HMAC verification → opaque session cookie → per-request validation against the new `admin_sessions` table. Tighten CORS to an allowlist.

**Architecture:** Login Widget POSTs its signed payload to `POST /api/auth/login`; server verifies HMAC-SHA256 against `sha256(bot_token)`, checks `user_id ∈ super_admins`, creates an `admin_sessions` row (30-day TTL) and sets a `Secure; HttpOnly; SameSite=Lax` cookie with a 32-byte opaque token. Every subsequent request resolves the cookie → session row → user_id; expired/missing/revoked → 401. CORS becomes an explicit allowlist sourced from env.

**Tech Stack:** FastAPI, SQLAlchemy 2.x async, Alembic, SvelteKit 2 + Svelte 5 runes, `hashlib` (stdlib only — no new deps).

---

## File Structure

| Path | Purpose |
|---|---|
| `alembic/versions/e4f5a6b7c8d9_add_admin_sessions.py` | Migration: `admin_sessions` table |
| `app/db/models.py` | `AdminSession` ORM model |
| `app/core/config.py` | New `WebApiSettings` (cookie flags, allowed_origins, session_ttl_days) |
| `app/webapi/auth/__init__.py` | Package init |
| `app/webapi/auth/telegram_login.py` | HMAC verification for Login Widget payload |
| `app/webapi/auth/session_store.py` | create/load/revoke session rows |
| `app/webapi/deps.py` | Replace `require_super_admin` stub with cookie-backed version |
| `app/webapi/routes/auth.py` | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| `app/webapi/main.py` | Wire `auth` router, CORS allowlist from settings |
| `app/webapi/schemas.py` | `TelegramLoginPayload`, `AuthMeResponse` |
| `webui/src/lib/stores/auth.svelte.ts` | Rune-backed auth store (me / loading / login / logout) |
| `webui/src/lib/components/TelegramLoginButton.svelte` | Iframe-based TG Login Widget wrapper |
| `webui/src/routes/login/+page.svelte` | Public login page — only route outside auth gate |
| `webui/src/routes/+layout.svelte` | Guard: redirect to `/login` on 401; Logout button in header |
| `webui/src/lib/api/client.ts` | `apiFetch`: on 401, push to `/login` (don't swallow) |
| `tests/unit/test_telegram_login_hmac.py` | HMAC happy path + tampering rejection |
| `tests/unit/test_admin_sessions.py` | ORM: create, expire, revoke |
| `tests/webapi/test_auth_routes.py` | Login, logout, /me, protected route 401 |

---

## Tasks

### Task 1 — Config: `WebApiSettings` + tighten CORS default

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1** — Add new settings class after `AdminSettings`:

```python
class WebApiSettings(BaseSettings):
    """Admin web UI / HTTP API configuration."""

    allowed_origins: list[str] = Field(
        default_factory=list,
        description="Comma-separated list of allowed Origin headers (e.g. https://admin.konnekt.example)",
    )
    session_ttl_days: int = Field(default=30, description="Admin session TTL in days")
    session_cookie_name: str = Field(default="konnekt_admin_session")
    session_cookie_secure: bool = Field(
        default=True,
        description="Set Secure flag on session cookie. Disable only for local http:// dev.",
    )
    session_cookie_samesite: str = Field(default="lax", description="SameSite: lax|strict|none")
    dev_bypass_auth: bool = Field(
        default=False,
        description="Dev-only: skip session validation, act as super_admins[0]. NEVER set in prod.",
    )

    model_config = SettingsConfigDict(
        env_prefix="WEBAPI_",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(s) for s in v]
        return []
```

- [ ] **Step 2** — Register in the aggregated `Settings` class (same pattern as other subclasses):

```python
webapi: WebApiSettings = Field(default_factory=WebApiSettings)
```

- [ ] **Step 3** — Append to `.env.example`:

```env
# --- Web admin UI ---
WEBAPI_ALLOWED_ORIGINS=http://localhost:5173
WEBAPI_SESSION_TTL_DAYS=30
WEBAPI_SESSION_COOKIE_SECURE=false   # true in production (HTTPS)
WEBAPI_DEV_BYPASS_AUTH=true          # dev-only; remove for prod
```

- [ ] **Step 4** — Run `uv run -m pytest tests/unit -k config -x`, expect pass.

- [ ] **Step 5** — Commit.

```bash
git add app/core/config.py .env.example
git commit -m "feat(config): add WebApiSettings (cors allowlist, session flags)"
```

---

### Task 2 — Migration: `admin_sessions` table

**Files:**
- Create: `alembic/versions/e4f5a6b7c8d9_add_admin_sessions.py`

- [ ] **Step 1** — Write migration:

```python
"""Add admin_sessions.

Opaque-token sessions for the web admin UI. session_id is a url-safe
random string (stored plaintext — it's already the secret, single-tenant
admin scope, no reason to hash). One row per active login.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-21 23:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False, index=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("admin_sessions")
```

- [ ] **Step 2** — Run `uv run alembic upgrade head`, verify no error.

- [ ] **Step 3** — Commit.

```bash
git add alembic/versions/e4f5a6b7c8d9_add_admin_sessions.py
git commit -m "feat(db): admin_sessions migration"
```

---

### Task 3 — `AdminSession` ORM model

**Files:**
- Modify: `app/db/models.py`

- [ ] **Step 1** — Add to end of file (after `SpamPing`):

```python
class AdminSession(Base):
    __tablename__ = "admin_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __init__(
        self,
        session_id: str,
        user_id: int,
        *,
        created_at: datetime.datetime,
        last_seen_at: datetime.datetime,
        expires_at: datetime.datetime,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = created_at
        self.last_seen_at = last_seen_at
        self.expires_at = expires_at
        self.user_agent = user_agent
        self.ip = ip
```

- [ ] **Step 2** — Write test `tests/unit/test_admin_sessions.py`:

```python
"""ORM-level coverage for AdminSession."""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import pytest
from app.db.models import AdminSession
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_create_and_read(session: AsyncSession) -> None:
    now = datetime.datetime(2026, 4, 22, 0, 0, 0)
    s = AdminSession(
        session_id="abc" * 10,
        user_id=1,
        created_at=now,
        last_seen_at=now,
        expires_at=now + datetime.timedelta(days=30),
    )
    session.add(s)
    await session.commit()

    row = (await session.execute(select(AdminSession).where(AdminSession.session_id == s.session_id))).scalar_one()
    assert row.user_id == 1
    assert row.user_agent is None


async def test_expired_flag(session: AsyncSession) -> None:
    past = datetime.datetime(2026, 1, 1, 0, 0, 0)
    s = AdminSession(
        session_id="expired",
        user_id=1,
        created_at=past,
        last_seen_at=past,
        expires_at=past + datetime.timedelta(days=30),
    )
    session.add(s)
    await session.commit()

    assert s.expires_at < datetime.datetime(2026, 4, 22)
```

- [ ] **Step 3** — Run `uv run -m pytest tests/unit/test_admin_sessions.py -x -v`, expect pass.

- [ ] **Step 4** — Commit.

```bash
git add app/db/models.py tests/unit/test_admin_sessions.py
git commit -m "feat(db): AdminSession ORM model + coverage"
```

---

### Task 4 — Telegram Login Widget HMAC verification

**Files:**
- Create: `app/webapi/auth/__init__.py` (empty)
- Create: `app/webapi/auth/telegram_login.py`
- Create: `tests/unit/test_telegram_login_hmac.py`

- [ ] **Step 1** — `app/webapi/auth/__init__.py` = empty.

- [ ] **Step 2** — `app/webapi/auth/telegram_login.py`:

```python
"""Telegram Login Widget signature verification.

Widget payload contract (per https://core.telegram.org/widgets/login#checking-authorization):

  1. Build a data-check-string = "\n".join(sorted(f"{k}={v}" for k,v in payload if k != 'hash'))
  2. secret = sha256(bot_token).digest()
  3. check_hash = hmac_sha256(secret, data_check_string).hexdigest()
  4. constant-time compare with payload['hash']; also reject if auth_date older than 24h.

Single-tenant; we additionally check user_id ∈ super_admins at the caller.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
from typing import TYPE_CHECKING

from app.core.exceptions import DomainError
from app.core.time import utc_now

if TYPE_CHECKING:
    from collections.abc import Mapping


class LoginWidgetError(DomainError):
    """Raised when a Telegram Login payload fails verification."""


_MAX_AUTH_AGE_SECONDS = 24 * 3600


def verify_login_payload(payload: Mapping[str, str], *, bot_token: str, now: datetime.datetime | None = None) -> int:
    """Return the authenticated ``user_id`` or raise :class:`LoginWidgetError`.

    Expected keys (all stringified by the widget): id, auth_date, hash; optional:
    first_name, last_name, username, photo_url.
    """
    if "hash" not in payload or "id" not in payload or "auth_date" not in payload:
        raise LoginWidgetError("missing required fields")
    claimed_hash = payload["hash"]

    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload) if k != "hash")
    secret = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, claimed_hash):
        raise LoginWidgetError("signature mismatch")

    try:
        auth_epoch = int(payload["auth_date"])
    except ValueError as err:
        raise LoginWidgetError("auth_date not an integer") from err
    current = now or utc_now()
    age_seconds = (current - datetime.datetime.fromtimestamp(auth_epoch, tz=datetime.UTC).replace(tzinfo=None)).total_seconds()
    if age_seconds > _MAX_AUTH_AGE_SECONDS or age_seconds < -300:
        raise LoginWidgetError("auth_date out of range")

    try:
        return int(payload["id"])
    except ValueError as err:
        raise LoginWidgetError("id not an integer") from err
```

- [ ] **Step 3** — `tests/unit/test_telegram_login_hmac.py`:

```python
"""Telegram Login Widget HMAC verification."""
from __future__ import annotations

import datetime
import hashlib
import hmac

import pytest
from app.webapi.auth.telegram_login import LoginWidgetError, verify_login_payload


def _sign(payload: dict[str, str], bot_token: str) -> str:
    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    secret = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


def test_valid_payload_returns_user_id() -> None:
    now = datetime.datetime(2026, 4, 22, 12, 0, 0)
    unsigned = {
        "id": "268388996",
        "auth_date": str(int(now.replace(tzinfo=datetime.UTC).timestamp())),
        "username": "azamat",
    }
    bot_token = "123:abc"
    unsigned["hash"] = _sign(unsigned, bot_token)

    assert verify_login_payload(unsigned, bot_token=bot_token, now=now) == 268388996


def test_tampered_payload_rejected() -> None:
    now = datetime.datetime(2026, 4, 22, 12, 0, 0)
    unsigned = {"id": "1", "auth_date": str(int(now.replace(tzinfo=datetime.UTC).timestamp()))}
    unsigned["hash"] = _sign(unsigned, "token-a")
    with pytest.raises(LoginWidgetError, match="signature"):
        verify_login_payload(unsigned, bot_token="token-b", now=now)


def test_old_auth_date_rejected() -> None:
    now = datetime.datetime(2026, 4, 22, 12, 0, 0)
    old = now - datetime.timedelta(hours=25)
    unsigned = {"id": "1", "auth_date": str(int(old.replace(tzinfo=datetime.UTC).timestamp()))}
    unsigned["hash"] = _sign(unsigned, "token")
    with pytest.raises(LoginWidgetError, match="auth_date"):
        verify_login_payload(unsigned, bot_token="token", now=now)


def test_missing_hash_rejected() -> None:
    with pytest.raises(LoginWidgetError, match="missing"):
        verify_login_payload({"id": "1", "auth_date": "1"}, bot_token="t")
```

- [ ] **Step 4** — Run `uv run -m pytest tests/unit/test_telegram_login_hmac.py -x -v`, expect 4 pass.

- [ ] **Step 5** — Commit.

```bash
git add app/webapi/auth/__init__.py app/webapi/auth/telegram_login.py tests/unit/test_telegram_login_hmac.py
git commit -m "feat(auth): Telegram Login Widget HMAC verification"
```

---

### Task 5 — Session store

**Files:**
- Create: `app/webapi/auth/session_store.py`

- [ ] **Step 1** — Write module:

```python
"""CRUD for ``admin_sessions``.

Session IDs are generated with :func:`secrets.token_urlsafe(32)` — 43 chars
of URL-safe base64 (~256 bits of entropy). Plaintext in DB: the cookie
itself is the secret and never leaves HTTPS+HttpOnly.
"""
from __future__ import annotations

import datetime
import secrets
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from app.core.time import utc_now
from app.db.models import AdminSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


async def create_session(
    session: AsyncSession,
    *,
    user_id: int,
    ttl_days: int,
    user_agent: str | None,
    ip: str | None,
) -> AdminSession:
    now = utc_now()
    row = AdminSession(
        session_id=new_session_id(),
        user_id=user_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + datetime.timedelta(days=ttl_days),
        user_agent=user_agent,
        ip=ip,
    )
    session.add(row)
    await session.commit()
    return row


async def load_valid_session(session: AsyncSession, session_id: str) -> AdminSession | None:
    """Return the row if present and not expired, else None. Bumps ``last_seen_at``."""
    row = (
        await session.execute(select(AdminSession).where(AdminSession.session_id == session_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    now = utc_now()
    if row.expires_at <= now:
        await session.delete(row)
        await session.commit()
        return None
    row.last_seen_at = now
    await session.commit()
    return row


async def revoke_session(session: AsyncSession, session_id: str) -> bool:
    row = (
        await session.execute(select(AdminSession).where(AdminSession.session_id == session_id))
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def purge_expired(session: AsyncSession) -> int:
    now = utc_now()
    result = await session.execute(delete(AdminSession).where(AdminSession.expires_at <= now))
    await session.commit()
    return result.rowcount or 0
```

- [ ] **Step 2** — Extend `tests/unit/test_admin_sessions.py` with:

```python
from app.webapi.auth import session_store


async def test_create_and_load_round_trip(session: AsyncSession) -> None:
    row = await session_store.create_session(session, user_id=1, ttl_days=30, user_agent="ua", ip="127.0.0.1")
    found = await session_store.load_valid_session(session, row.session_id)
    assert found is not None and found.user_id == 1


async def test_load_expired_removes_row(session: AsyncSession) -> None:
    row = await session_store.create_session(session, user_id=1, ttl_days=30, user_agent=None, ip=None)
    # Expire it.
    row.expires_at = datetime.datetime(2026, 1, 1)
    await session.commit()
    assert await session_store.load_valid_session(session, row.session_id) is None
    # And row is deleted.
    assert await session_store.load_valid_session(session, row.session_id) is None


async def test_revoke(session: AsyncSession) -> None:
    row = await session_store.create_session(session, user_id=1, ttl_days=30, user_agent=None, ip=None)
    assert await session_store.revoke_session(session, row.session_id) is True
    assert await session_store.revoke_session(session, row.session_id) is False
```

- [ ] **Step 3** — Run `uv run -m pytest tests/unit/test_admin_sessions.py -x -v`, expect pass.

- [ ] **Step 4** — Commit.

```bash
git add app/webapi/auth/session_store.py tests/unit/test_admin_sessions.py
git commit -m "feat(auth): admin session store"
```

---

### Task 6 — Wire cookie validation into `require_super_admin`

**Files:**
- Modify: `app/webapi/deps.py`

- [ ] **Step 1** — Replace the stubbed dep:

```python
from fastapi import HTTPException, Request


async def require_super_admin(request: Request) -> int:
    """Validate the session cookie; return the authenticated super-admin's user_id.

    Cookie name is ``settings.webapi.session_cookie_name``. Reading via
    ``request.cookies.get(name)`` keeps the name config-driven (FastAPI's
    ``Cookie(alias=...)`` would bake it into the signature at import time).
    """
    from app.core.config import settings
    from app.webapi.auth import session_store

    if not settings.admin.super_admins:
        raise HTTPException(status_code=503, detail="No super_admin configured")

    if settings.webapi.dev_bypass_auth:
        return settings.admin.super_admins[0]

    token = request.cookies.get(settings.webapi.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    # Fresh DB session — depending on `get_session` at this layer would create
    # a circular import, and this path is lightweight.
    from app.db.session import create_session_maker

    async with create_session_maker()() as db:
        row = await session_store.load_valid_session(db, token)
        if row is None or row.user_id not in settings.admin.super_admins:
            raise HTTPException(status_code=401, detail="invalid session")
        return row.user_id
```

- [ ] **Step 2** — In `tests/conftest.py`, add `"WEBAPI_DEV_BYPASS_AUTH": "true"` to the `os.environ.update({...})` block at top of file. This preserves existing test behavior (dev no-op) without touching individual fixtures. The new auth-route tests (Task 7) explicitly flip it back to False on their own fixture.

- [ ] **Step 3** — Run `uv run -m pytest tests/webapi -x`. Expect all-green (same count as before plus the new auth tests later).

- [ ] **Step 4** — Commit.

```bash
git add app/webapi/deps.py tests/conftest.py
git commit -m "feat(auth): cookie-backed require_super_admin (dev bypass via flag)"
```

---

### Task 7 — Auth routes + schemas

**Files:**
- Modify: `app/webapi/schemas.py`
- Create: `app/webapi/routes/auth.py`

- [ ] **Step 1** — Add schemas:

```python
class TelegramLoginPayload(BaseModel):
    """Payload POSTed by the Telegram Login Widget. Extra keys are preserved so HMAC verifies."""
    model_config = ConfigDict(extra="allow")

    id: int
    auth_date: int
    hash: str


class AuthMeResponse(BaseModel):
    user_id: int
    is_authenticated: bool = True
```

- [ ] **Step 2** — `app/webapi/routes/auth.py`:

```python
"""Authentication routes: Telegram Login Widget → session cookie."""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import settings
from app.core.logging import get_logger
from app.webapi.auth import session_store
from app.webapi.auth.telegram_login import LoginWidgetError, verify_login_payload
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import AuthMeResponse, TelegramLoginPayload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger("webapi.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    payload: TelegramLoginPayload,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthMeResponse:
    # Dump dict with extras so HMAC sees the whole payload.
    raw = {k: str(v) for k, v in payload.model_dump().items()}
    try:
        user_id = verify_login_payload(raw, bot_token=settings.telegram.token)
    except LoginWidgetError as err:
        logger.warning("login_widget_rejected", reason=str(err))
        raise HTTPException(status_code=401, detail="login failed") from err

    if user_id not in settings.admin.super_admins:
        logger.warning("login_non_admin", user_id=user_id)
        raise HTTPException(status_code=403, detail="not authorized")

    row = await session_store.create_session(
        session,
        user_id=user_id,
        ttl_days=settings.webapi.session_ttl_days,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    response.set_cookie(
        key=settings.webapi.session_cookie_name,
        value=row.session_id,
        max_age=settings.webapi.session_ttl_days * 86400,
        secure=settings.webapi.session_cookie_secure,
        httponly=True,
        samesite=settings.webapi.session_cookie_samesite,
        path="/",
    )
    return AuthMeResponse(user_id=user_id)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    token = request.cookies.get(settings.webapi.session_cookie_name)
    if token:
        await session_store.revoke_session(session, token)
    response.delete_cookie(settings.webapi.session_cookie_name, path="/")


@router.get("/me")
async def me(user_id: Annotated[int, Depends(require_super_admin)]) -> AuthMeResponse:
    return AuthMeResponse(user_id=user_id)
```

- [ ] **Step 3** — Register in `app/webapi/main.py`:

```python
from app.webapi.routes import agent, auth, channels, chats, costs, health, posts, spam, stats
...
app.include_router(auth.router, prefix="/api")
```

- [ ] **Step 4** — Tighten CORS to settings allowlist. Add `from app.core.config import settings` to `main.py`, then replace the `allow_origin_regex=".*"` line:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.webapi.allowed_origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 5** — Write `tests/webapi/test_auth_routes.py`:

```python
"""Auth route coverage."""
from __future__ import annotations

import datetime
import hashlib
import hmac
from typing import TYPE_CHECKING

import pytest
from app.core.config import settings
from app.webapi.main import app
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


def _sign(payload: dict[str, str], token: str) -> str:
    data_check = "\n".join(f"{k}={payload[k]}" for k in sorted(payload))
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def client_factory(db_session_maker: async_sessionmaker[AsyncSession]):
    from app.webapi.deps import get_session

    async def _override_session():
        async with db_session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    settings.admin.super_admins = [268388996]
    settings.telegram.token = "test:bot:token"
    settings.webapi.dev_bypass_auth = False
    settings.webapi.session_cookie_secure = False
    transport = ASGITransport(app=app)

    def make() -> AsyncClient:
        return AsyncClient(transport=transport, base_url="http://test")

    yield make
    app.dependency_overrides.pop(get_session, None)
    settings.webapi.dev_bypass_auth = True


async def test_me_unauthenticated_returns_401(client_factory) -> None:
    async with client_factory() as client:
        resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_full_login_flow(client_factory) -> None:
    now_s = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    payload = {"id": 268388996, "auth_date": now_s, "first_name": "A"}
    # Sign after stringifying — matches widget serialization.
    str_payload = {k: str(v) for k, v in payload.items()}
    str_payload["hash"] = _sign(str_payload, "test:bot:token")

    async with client_factory() as client:
        resp = await client.post("/api/auth/login", json={**payload, "hash": str_payload["hash"]})
        assert resp.status_code == 200, resp.text
        assert resp.cookies.get(settings.webapi.session_cookie_name)

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"] == 268388996

        out = await client.post("/api/auth/logout")
        assert out.status_code == 204


async def test_non_admin_rejected(client_factory) -> None:
    now_s = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    payload = {"id": 99999, "auth_date": now_s}
    str_payload = {k: str(v) for k, v in payload.items()}
    str_payload["hash"] = _sign(str_payload, "test:bot:token")
    async with client_factory() as client:
        resp = await client.post("/api/auth/login", json={**payload, "hash": str_payload["hash"]})
    assert resp.status_code == 403
```

- [ ] **Step 6** — Run `uv run -m pytest tests/webapi/test_auth_routes.py -x -v`, expect 3 pass.

- [ ] **Step 7** — Full suite: `uv run -m pytest -x`. Fix any regressions caused by the dev_bypass flag default.

- [ ] **Step 8** — Commit.

```bash
git add app/webapi/schemas.py app/webapi/routes/auth.py app/webapi/main.py tests/webapi/test_auth_routes.py
git commit -m "feat(auth): /api/auth login + logout + me; tighten CORS"
```

---

### Task 8 — OpenAPI regen + FE auth store

**Files:**
- Modify: `webui/src/lib/api/types.ts` (auto-gen)
- Create: `webui/src/lib/stores/auth.svelte.ts`

- [ ] **Step 1** — `cd webui && pnpm run api:sync` (starts backend briefly + regens types).

- [ ] **Step 2** — Write `webui/src/lib/stores/auth.svelte.ts`:

```ts
import { apiFetch } from '$lib/api/client';
import type { components } from '$lib/api/types';

type Me = components['schemas']['AuthMeResponse'];

type AuthState = {
  me: Me | null;
  loading: boolean;
  initialized: boolean;
};

const state = $state<AuthState>({ me: null, loading: false, initialized: false });

export const auth = {
  get me() {
    return state.me;
  },
  get loading() {
    return state.loading;
  },
  get initialized() {
    return state.initialized;
  },
  async refresh(): Promise<void> {
    state.loading = true;
    try {
      const res = await apiFetch<Me>('/api/auth/me');
      state.me = res.data ?? null;
    } finally {
      state.loading = false;
      state.initialized = true;
    }
  },
  async logout(): Promise<void> {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    state.me = null;
  },
};
```

- [ ] **Step 3** — Commit.

```bash
git add webui/src/lib/api/types.ts webui/src/lib/stores/auth.svelte.ts
git commit -m "feat(webui): auth store + regen OpenAPI types"
```

---

### Task 9 — Telegram Login Widget component + /login route

**Files:**
- Create: `webui/src/lib/components/TelegramLoginButton.svelte`
- Create: `webui/src/routes/login/+page.svelte`

- [ ] **Step 1** — `TelegramLoginButton.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';

  type Props = {
    botUsername: string;
    onAuth: (payload: Record<string, string | number>) => void;
  };
  let { botUsername, onAuth }: Props = $props();

  let container: HTMLDivElement;

  onMount(() => {
    // The widget calls window.onTelegramAuth(user) globally — bridge it.
    (window as unknown as { onTelegramAuth: (u: Record<string, string | number>) => void }).onTelegramAuth = onAuth;

    const s = document.createElement('script');
    s.async = true;
    s.src = 'https://telegram.org/js/telegram-widget.js?22';
    s.setAttribute('data-telegram-login', botUsername);
    s.setAttribute('data-size', 'large');
    s.setAttribute('data-radius', '8');
    s.setAttribute('data-onauth', 'onTelegramAuth(user)');
    s.setAttribute('data-request-access', 'write');
    container.appendChild(s);
  });
</script>

<div bind:this={container}></div>
```

- [ ] **Step 2** — `webui/src/routes/login/+page.svelte`:

```svelte
<script lang="ts">
  import { goto } from '$app/navigation';
  import { apiFetch } from '$lib/api/client';
  import TelegramLoginButton from '$lib/components/TelegramLoginButton.svelte';
  import { auth } from '$lib/stores/auth.svelte';

  const BOT_USERNAME = 'konnekt_moder_bot';
  let error = $state<string | null>(null);

  async function handleAuth(user: Record<string, string | number>): Promise<void> {
    error = null;
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(user),
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.error) {
      error = res.error.message ?? 'Login failed';
      return;
    }
    await auth.refresh();
    await goto('/');
  }
</script>

<div class="flex min-h-screen items-center justify-center bg-zinc-50 px-4">
  <div class="w-full max-w-sm space-y-4 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
    <h1 class="text-lg font-semibold tracking-tight">Konnekt Admin</h1>
    <p class="text-sm text-zinc-500">Sign in with your Telegram account to continue.</p>
    <TelegramLoginButton botUsername={BOT_USERNAME} onAuth={handleAuth} />
    {#if error}
      <p class="text-xs text-red-600">{error}</p>
    {/if}
  </div>
</div>
```

- [ ] **Step 3** — Commit.

```bash
git add webui/src/lib/components/TelegramLoginButton.svelte webui/src/routes/login/+page.svelte
git commit -m "feat(webui): /login page + Telegram Login Widget"
```

---

### Task 10 — Gate the rest of the app + header logout

**Files:**
- Modify: `webui/src/routes/+layout.svelte`
- Modify: `webui/src/lib/api/client.ts`

- [ ] **Step 1** — In `client.ts`, on 401 from any call other than `/api/auth/*`, redirect:

```ts
// inside apiFetch, after `const resp = await fetch(...)`:
if (resp.status === 401 && !url.startsWith('/api/auth')) {
  const { goto } = await import('$app/navigation');
  void goto('/login');
}
```

- [ ] **Step 2** — In `+layout.svelte`, run `auth.refresh()` on mount, show a lightweight splash while `!auth.initialized`, and render a Logout button that clears state + goes to `/login`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { auth } from '$lib/stores/auth.svelte';
  // ... existing imports

  onMount(() => {
    if ($page.url.pathname !== '/login') void auth.refresh();
  });

  async function doLogout(): Promise<void> {
    await auth.logout();
    await goto('/login');
  }
</script>

{#if $page.url.pathname === '/login'}
  <slot />
{:else if !auth.initialized}
  <div class="flex min-h-screen items-center justify-center text-sm text-zinc-400">Loading…</div>
{:else if !auth.me}
  <!-- apiFetch already kicked off /login navigation; render nothing -->
{:else}
  <!-- existing shell here, plus: -->
  <button onclick={doLogout} class="text-xs text-zinc-500 hover:text-zinc-800">Logout</button>
  <slot />
{/if}
```

Preserve the existing nav/header — this task wraps, it does not replace.

- [ ] **Step 3** — Run `cd webui && pnpm run check`, expect 0 errors.

- [ ] **Step 4** — Manual verification: start backend (`uv run uvicorn app.webapi.main:app --reload --port 8787`) + `pnpm run dev` in webui; visit `http://localhost:5173/` → should redirect to `/login`. Set `WEBAPI_DEV_BYPASS_AUTH=true` in `.env` → should pass through. Unset → back to redirect.

- [ ] **Step 5** — Commit.

```bash
git add webui/src/routes/+layout.svelte webui/src/lib/api/client.ts
git commit -m "feat(webui): auth-gated layout + 401 redirect + logout"
```

---

### Task 11 — Final sweep + PR

- [ ] **Step 1** — `uv run ruff check app tests && uv run ruff format --check app tests && uv run ty check app tests`, expect clean (same ty baseline as before: 7 diagnostics).

- [ ] **Step 2** — `uv run -m pytest -x`, expect all green.

- [ ] **Step 3** — `cd webui && pnpm run check`, expect 0 errors.

- [ ] **Step 4** — Push & open PR.

```bash
git push -u origin webui/phase-4a-auth
gh pr create --title "feat(webui): Phase 4a — Telegram Login auth + session cookies" --body "..."
```

PR body: summarize the flow, call out dev_bypass flag + cookie flags + CORS tightening, list follow-up (Phase 4b mutations).

---

## Out of Scope (Phase 4b)

- Approve/reject/edit post mutations
- Channel CRUD mutations
- Ban/unban / blacklist mutations
- `/settings` page functionality
- Rate limiting / brute-force protection on `/auth/login` (single-tenant; acceptable for 4a)
