# Architecture Review -- moderator-bot

**Date:** 2026-03-06
**Reviewer:** Claude Opus 4.6 (automated)
**Commit:** `670b1ca` (branch `claude/telegram-chat-bot-JfIPd`)
**Scope:** Full codebase (`app/`, `tests/`, `pyproject.toml`)

---

## Executive Summary

The project demonstrates a well-structured DDD approach with clear layer separation, modern async patterns, and solid test infrastructure (279 tests). However, the DDD migration is incomplete: ORM models still contain business logic that duplicates domain entities, repositories commit their own transactions (breaking Unit-of-Work), and the application service layer mixes two incompatible styles (procedural functions vs. injected class-based services). Datetime handling is inconsistent across the codebase, and the `BlacklistMiddleware` queries all blocked users on every incoming message.

---

## Quick Wins (low effort, high impact)

| # | File(s) | Fix |
|---|---------|-----|
| 1 | `app/infrastructure/db/models.py` | Replace all `default=datetime.datetime.now` with `default=datetime.datetime.now` **wrapped in a lambda** or use `func.now()`. Current code calls `.now` at class-load time, not at insert time -- every row gets the same timestamp. |
| 2 | `app/presentation/telegram/middlewares/black_list.py` | Cache blocked user IDs (same pattern as `ManagedChatsMiddleware`) instead of `SELECT *` on every message. |
| 3 | `app/agent/escalation.py` | Replace deprecated `datetime.datetime.utcnow()` with `datetime.datetime.now(datetime.UTC)` (4 call sites). |
| 4 | `app/presentation/telegram/utils/other.py` | `get_user_mention`, `get_chat_mention`, etc. are `async def` but contain no awaits. Drop `async` to avoid unnecessary coroutine overhead. |
| 5 | `app/domain/models.py` | Delete shim file. It re-exports ORM models from `domain/` which violates DDD -- infrastructure should never leak into domain. Callers should import from `app.infrastructure.db.models`. |

---

## Detailed Findings

### 1. DDD Compliance

#### P0 -- Domain layer imports infrastructure

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P0 | DDD | `app/domain/models.py` | The domain package re-exports SQLAlchemy ORM models (`Admin`, `User`, `Chat`, etc.) from `app.infrastructure.db.models`. This makes the domain layer depend on infrastructure, defeating the purpose of DDD layering. Any code that does `from app.domain.models import User` is silently pulling in SQLAlchemy. | Delete `app/domain/models.py`. Grep for all imports and repoint them to `app.infrastructure.db.models`. The shim was introduced for backward compatibility; the migration should be completed. |

#### P1 -- ORM models duplicate domain entity logic

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | DDD | `app/infrastructure/db/models.py`, `app/domain/entities.py` | ORM `User` has `block()`, `unblock()`, `display_name`, `is_blocked`. Domain `UserEntity` has identical methods. Same duplication exists for `Chat`, `ChatLink`, `Message`. Business logic lives in two places. | Strip ORM models to data-only (columns + `__init__`). All business logic should live exclusively in domain entities. Repositories should map ORM <-> entity and only entity methods should be called by services. |

#### P1 -- `display_name` implemented three times

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | DDD/DRY | `app/domain/entities.py:22`, `app/domain/value_objects.py:108`, `app/infrastructure/db/models.py:154` | The `display_name` property is implemented identically in `UserEntity`, `UserProfile` value object, and ORM `User` model. Additionally, `agent_handler.py:96-100` has inline display-name logic. | Canonicalize in `UserEntity.display_name`. Remove from ORM model and value object. Handler should use the entity method. |

#### P1 -- Application services use two incompatible patterns

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Architecture | `app/application/services/` | `UserService` and `ModerationService` are proper classes accepting repository interfaces via DI. `moderation.py`, `spam.py`, `history.py`, `report.py` are procedural modules that instantiate concrete repositories themselves (`UserRepository(db)`), bypassing DI entirely. | Migrate procedural services to class-based services with constructor-injected repository interfaces, or at minimum, accept repository interfaces as parameters instead of constructing concrete implementations. |

#### P1 -- Agent layer bypasses repository abstraction

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | DDD | `app/agent/memory.py`, `app/agent/escalation.py` | Both modules use raw SQLAlchemy queries against ORM models (`AgentDecision`, `AgentEscalation`) directly -- no repository interface, no entity mapping. This couples the agent layer tightly to the database schema. | Create `IAgentDecisionRepository` and `IAgentEscalationRepository` interfaces in the domain layer, implement in infrastructure, inject into agent services. |

#### P2 -- Value objects defined but never used

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | DDD | `app/domain/value_objects.py` | `UserId`, `ChatId`, `MessageId`, `WelcomeSettings`, `UserProfile` value objects are defined but never used by entities or repositories. Entities use raw `int` for IDs. Only `MuteDuration` and `ModerationAction` are used. | Either adopt value objects in entities and repository interfaces (proper DDD), or remove unused ones to reduce dead code. |

---

### 2. Code Quality

#### P0 -- `datetime.datetime.now` used as column default (mutable default bug)

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P0 | Bug | `app/infrastructure/db/models.py` (lines 44, 46, 106, 108, 211, 259, 280, 321, 375, 419) | `default=datetime.datetime.now` passes the **function object** as default, which SQLAlchemy calls on each insert. This is actually correct for SQLAlchemy -- SQLAlchemy calls the callable. However, `onupdate=datetime.datetime.now` works the same way. **But** these produce naive datetimes with no timezone, while `escalation.py` uses `utcnow()`. This mismatch means timestamps from different parts of the system are incomparable if the server is not in UTC. | Standardize on `datetime.datetime.now(datetime.UTC)` everywhere, or use `func.now()` for database-server timestamps. Pick one approach and apply consistently. |

#### P0 -- `BlacklistMiddleware` does full table scan per message

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P0 | Performance | `app/presentation/telegram/middlewares/black_list.py` | Every incoming message triggers `SELECT * FROM users WHERE blocked = true`, loads all blocked user objects, builds a set, then checks membership. In a busy group with thousands of blocked users, this is a per-message database round-trip with full deserialization. | Add a TTL cache (like `ManagedChatsMiddleware` already does), or query `SELECT 1 FROM users WHERE id = ? AND blocked = true` for just the current user. |

#### P1 -- Legacy methods on repositories

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Tech Debt | `app/infrastructure/db/repositories/user.py` (87-105), `chat.py` (78-113), `admin.py` (63-75), `chat_link.py` (60-62) | Every repository has "Legacy methods for backward compatibility" that return ORM models instead of domain entities, bypass the entity mapping layer, and duplicate interface methods. `ChatRepository.get_chats()` returns `list[Chat]` while `get_all()` returns `list[ChatEntity]`. | Migrate all callers to use the entity-based interface methods. Delete legacy methods. Key callers: `moderation.py:54` (`get_chats()`), `admin.py:44` (`get_db_admins()`), `buttons.py:21` (`get_chat_links()`). |

#### P1 -- Broad `except Exception` everywhere

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Error Handling | ~40 sites across `app/` | Almost every try/except catches bare `Exception`. In handlers like `moderation.py:92`, user-facing error messages expose raw exception text (`f"Произошла ошибка:\n\n{err}"`), leaking internal details to users. | Catch specific exceptions (`TelegramBadRequest`, `TelegramForbiddenError`, `SQLAlchemyError`). Show generic user-facing messages. Log full details server-side. |

#### P1 -- `AdminMiddleware` and `AnyAdminMiddleware` are nearly identical

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | DRY | `app/presentation/telegram/middlewares/admin.py` | `AdminMiddleware` (lines 36-49) and `AnyAdminMiddleware` (lines 52-66) have identical logic. The only difference is the error message. `AnyAdminMiddleware` is never actually used in production code. | Remove `AnyAdminMiddleware` if unused, or merge into a single parameterized middleware. |

#### P2 -- Unnecessary `async` on pure synchronous functions

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Async | `app/presentation/telegram/utils/other.py` | `get_user_mention`, `get_chat_mention`, `get_message_mention`, `get_message_link`, `get_chat_link` are all `async def` but contain zero `await` expressions. Creating coroutines for synchronous operations adds overhead. | Change to regular `def`. This requires updating all `await` calls to direct calls, but it is straightforward. |

#### P2 -- `moderation.py` (handlers) has duplicate reply-check boilerplate

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | DRY | `app/presentation/telegram/handlers/moderation.py` | Every handler (`mute_user`, `unmute_user`, `ban_user`, `unban_user`, `full_ban`, `label_spam`) repeats the same pattern: check `message.reply_to_message`, check `from_user`, show error. 6 handlers x ~8 lines each. | Extract a decorator or aiogram filter that validates `reply_to_message` + `from_user` and injects the target user. |

#### P3 -- `calculate_mute_duration` silently defaults on parse failure

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P3 | Bug-risk | `app/presentation/telegram/utils/other.py:71` | `parsed.group(2)` can be `None` if regex doesn't match (returns `None` for no-match on the full pattern). The `int(parsed.group(2) or 5)` is fine, but `parsed` itself can be `None` if the regex doesn't match at all, causing `AttributeError`. The handler catches `Exception` generically. | Add explicit `None` check on `parsed` with a clear error message. |

---

### 3. Async Patterns

#### P1 -- Repositories commit inside their methods (breaks Unit of Work)

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Async/DB | All repositories (`user.py`, `chat.py`, `admin.py`, `message.py`, `chat_link.py`) | Every repository `save()`, `add_message()`, `delete()` method calls `await self.db.commit()` internally. This means each repository method is its own transaction. If a service needs to save a user AND a message atomically, it cannot -- each commits independently. | Move commit responsibility to the caller (service or middleware). Repositories should only `add()` and `flush()`. The `DependenciesMiddleware` session context should commit on success and rollback on failure. |

#### P1 -- `DependenciesMiddleware` creates session but never commits/rollbacks explicitly

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | DB | `app/presentation/telegram/middlewares/dependencies.py` | The middleware creates a session via `async with self.session_pool() as session` and passes it to handlers. But it never explicitly commits or rolls back. It relies on each repository method committing individually (see above). If a handler fails mid-way, some changes are committed and others are not, leaving the database in an inconsistent state. | Wrap handler call in a try/except. Commit after successful handler execution, rollback on exception. This gives you true request-scoped transactions. |

#### P2 -- `ModerationService.mute_user` imports `datetime` inside method body

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Code Quality | `app/application/services/moderation_service.py:38` | `import datetime` inside `mute_user()`. Same issue at line 86 with `from aiogram.types import ChatPermissions` (already imported at module top). | Move imports to module level. |

#### P2 -- `sleep_and_delete` creates fire-and-forget coroutines

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Async | `app/presentation/telegram/utils/other.py:9-12` | `sleep_and_delete` is awaited by callers, blocking the handler for `seconds` (up to 60s in some call sites before it returns). This ties up the handler coroutine unnecessarily. | Use `asyncio.create_task()` at the call site instead of `await`, so the handler returns immediately and the deletion happens in the background. Some call sites already return after calling this, but the `await` still blocks. |

#### P3 -- Global mutable state in `session.py`

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P3 | Architecture | `app/infrastructure/db/session.py` | `engine` and `sessionmaker` are module-level globals mutated by `create_session_maker()` and `close_db()`. This makes testing harder and introduces subtle state between test runs. | Encapsulate in a class or pass engine/sessionmaker explicitly. The DI container already holds the session maker. |

---

### 4. Testing Quality

#### P1 -- No tests for agent layer (`AgentCore`, `EscalationService`, `AgentMemory`)

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Testing | `app/agent/core.py`, `app/agent/escalation.py`, `app/agent/memory.py` | The e2e tests in `tests/e2e/test_agent_moderation.py` mock the PydanticAI agent entirely, so `AgentCore._execute()`, `AgentCore._build_user_prompt()`, and the memory/escalation database operations are never tested in isolation. `AgentMemory.get_user_risk_profile()` has complex SQL logic with no unit test. | Add unit tests for `AgentMemory` (test with SQLite), `EscalationService.create/resolve/timeout`, and `AgentCore._execute` (mock bot, real DB). |

#### P1 -- No tests for `moderation.py` service (the procedural one)

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Testing | `app/application/services/moderation.py` | `add_to_blacklist` and `remove_from_blacklist` are critical functions (ban across all chats, delete messages). No unit or integration test covers them. | Add tests with mocked bot and real DB session. Verify that banning happens across all registered chats, and that message deletion is attempted for each stored message. |

#### P2 -- Test isolation risk with `conftest.py` nested transactions

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Testing | `tests/conftest.py:66-72` | Nested transactions (savepoints) with SQLite can behave differently than PostgreSQL. SQLite's savepoint support is limited. If repositories call `commit()` inside a savepoint, the savepoint is consumed and subsequent operations may not roll back correctly. | Verify that test isolation actually works by adding a test that writes data and checking the next test sees a clean DB. Consider using a fresh engine per test (already the case since `engine` fixture is function-scoped). |

#### P2 -- `ModerationService` class has tests but never used in production handlers

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Testing/Arch | `app/application/services/moderation_service.py`, `tests/unit/test_moderation_service.py` | `ModerationService` is a well-designed class-based service with proper DI, but production handlers in `moderation.py` (handler) use the procedural `app.application.services.moderation` module instead. The class exists alongside the procedural module and is only used in tests. | Either migrate handlers to use `ModerationService` (preferred, better testability) or remove the class to reduce confusion. |

#### P2 -- Channel agent has limited test coverage

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Testing | `app/agent/channel/` | `tests/unit/test_channel_agent_v2.py` exists, but the orchestrator, source_discovery, feedback, cost_tracker, and publisher modules have no dedicated tests. | Add unit tests for `_next_scheduled_time`, source health tracking logic, and the screening pipeline. |

#### P3 -- Tests use `os.environ.update` at module level

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P3 | Testing | `tests/conftest.py:7-18` | Environment variables set at import time affect all tests and cannot be overridden per-test. The `settings` singleton is created at import time from these envvars. | Use `monkeypatch.setenv` in fixtures, or use `pydantic-settings` override mechanisms. The current approach works but is fragile if test order changes. |

---

### 5. Dependency Management

#### P2 -- `psycopg2-binary` is installed but never used

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Deps | `pyproject.toml:20` | `psycopg2-binary>=2.9` is listed as a dependency, but the codebase uses `asyncpg` for async connections and Alembic's sync URL uses the plain `postgresql://` scheme (which would use `psycopg2`). If Alembic actually uses it, it should be a dev dependency. | Move to dev dependencies if only Alembic needs it, or remove if Alembic uses asyncpg. |

#### P2 -- `pytz` is used but `zoneinfo` is available in Python 3.12+

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Deps | `app/presentation/telegram/utils/other.py:6` | `from pytz import timezone` is used for a single timezone conversion. Python 3.12+ ships `zoneinfo` in the stdlib, making `pytz` unnecessary. | Replace with `from zoneinfo import ZoneInfo` and `ZoneInfo("Europe/Prague")`. Remove `pytz` and `types-pytz` from dependencies. |

#### P3 -- `python-dotenv` likely redundant with `pydantic-settings`

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P3 | Deps | `pyproject.toml:24` | `pydantic-settings` already reads `.env` files natively (configured via `env_file=".env"` in every settings class). `python-dotenv` may be unused. | Grep for `dotenv` usage. If none, remove. |

---

### 6. Security Observations

#### P1 -- Default `WEBAPP_API_SECRET` in config

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P1 | Security | `app/core/config.py:108` | `api_secret: str = Field(default="your-secret-key", ...)` ships with a well-known default secret. If the operator forgets to set the env var, the webapp API is "protected" by a public secret. | Remove the default, making it a required field (no default). Or validate at startup that it is not the placeholder string. |

#### P2 -- Error messages expose internals to Telegram users

| Priority | Category | File(s) | Finding | Recommendation |
|----------|----------|---------|---------|----------------|
| P2 | Security | `app/presentation/telegram/handlers/moderation.py:93,122,141,162` | Patterns like `await message.answer(f"Произошла ошибка:\n\n{err}")` send raw Python exception text (which may include DB connection strings, SQL, or stack traces) to the Telegram chat. | Log the full error server-side. Show a generic "An error occurred" message to the user. |

---

## Summary Statistics

| Priority | Count |
|----------|-------|
| P0       | 3     |
| P1       | 13    |
| P2       | 12    |
| P3       | 4     |
| **Total** | **32** |

### Strengths

- Clean domain entity design (pure dataclasses, no framework deps)
- Repository interface pattern properly defined in domain layer
- Comprehensive test infrastructure with fake Telegram server for e2e tests
- Structured logging with contextual information
- Well-configured tooling (ruff, mypy strict mode, pre-commit)
- Agent layer is well-designed with learning-from-corrections capability
- Good use of Pydantic for configuration management

### Top 5 Priorities for Next Sprint

1. **Fix `BlacklistMiddleware` performance** -- per-message full table scan is a production risk
2. **Standardize datetime handling** -- mixed `utcnow()` / `now()` / naive datetimes will cause bugs
3. **Complete repository migration** -- delete legacy methods, make all callers use entity-based interfaces
4. **Add Unit-of-Work pattern** -- move commit out of repositories into middleware/service layer
5. **Delete `app/domain/models.py`** -- complete the DDD migration by removing the infrastructure shim from domain
