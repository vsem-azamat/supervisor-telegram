# Testing Strategy

Supervisor Telegram uses separate test lanes so fast feedback stays fast while
database and Telegram behavior can still be verified at the right boundary.

## Documentation-Driven TDD

For behavior changes:

1. Update the relevant domain document.
2. Add or update a failing test for the new rule.
3. Implement the smallest code change that passes.
4. Refactor after the behavior is documented and protected.

Choose the first failing test from the narrowest lane that can prove the rule.

## Test Lanes

### Unit Tests

Command:

```bash
uv run pytest tests/unit
```

Use for:

- pure functions and formatting rules;
- service logic with mocked external boundaries;
- scheduling calculations and branch-heavy behavior that does not need a real
  database.

SQLite-backed fixtures are acceptable when the rule does not depend on
PostgreSQL-specific semantics.

### PostgreSQL Integration Tests

Command:

```bash
uv run pytest tests/integration
```

Use for:

- repository behavior;
- Alembic-sensitive persistence paths;
- PostgreSQL-only features such as pgvector;
- constraints, indexes, cascades, and query behavior that SQLite cannot prove.

Integration tests use the PostgreSQL 18 pgvector testcontainer image. Prefer
this lane whenever the implementation claim depends on PostgreSQL behavior.

### Telegram End-To-End Tests

Command:

```bash
uv run pytest tests/e2e
```

Use for:

- full moderator or review workflows;
- Telegram callback flows;
- assertions about Bot API requests made across the workflow.

These tests use `FakeTelegramServer`. They prove local workflow behavior without
calling real Telegram.

### Web API Tests

Command:

```bash
uv run pytest tests/webapi
```

Use for:

- public/admin route contracts;
- auth boundaries;
- response projections;
- mutation behavior exposed through FastAPI.

When a web UI change only rearranges client presentation, use frontend checks in
addition to the API tests rather than forcing the behavior into backend tests.

## Test Authoring Rules

- Add the smallest test that fails for the right reason.
- Prefer unit tests first when the rule is local.
- Use PostgreSQL integration tests for database guarantees, not broad workflow
  coverage.
- Use E2E tests for user-visible flows, not as the first place to encode every
  domain rule.
- Create only the data each test needs.
- Mock external APIs unless the test explicitly targets the boundary itself.

## Verification

Use the narrowest command that proves the change, then widen when risk warrants
it:

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run ty check app tests
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/e2e
uv run pytest tests/webapi
pnpm --dir webui run check
pnpm --dir webui run build
```

CI runs linting, formatting, typing, the full pytest suite with coverage, and
the web UI checks.
