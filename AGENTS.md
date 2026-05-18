# Supervisor Telegram Engineering Rules

This file is the working contract for AI agents and developers in this
repository. It is not a setup guide or a product brief. Use `README.md` and
`docs/` for those.

## Documentation-Driven TDD

When behavior changes:

1. Update the canonical documentation first.
2. Add or update a failing test that captures the documented rule.
3. Implement the smallest code change that makes the test pass.
4. Refactor only after the documented behavior is protected by tests.

Use this loop for product behavior, domain rules, auth/security boundaries,
database semantics, and externally visible API or UI behavior.

Do not require a documentation update for typo fixes, purely mechanical
refactors, or internal cleanup that preserves existing contracts.

Use the documentation hierarchy from `docs/README.md`:

- `docs/product/` defines business intent, product scope, and the users we serve.
- `docs/domain/` owns current behavioral rules.
- `docs/architecture.md` explains code structure and technical decisions.
- `docs/testing/` defines the verification strategy.
- `docs/project/` stores operational learnings, not canonical product rules.

If implementation, tests, and canonical docs disagree, stop and reconcile the
contract before continuing.

## Core Operating Loop

1. Inspect the current checkout before proposing or editing.
2. State assumptions when they affect architecture, data, security, or delivery.
3. Make the smallest change that fixes the real problem.
4. Prefer red-green-refactor when behavior changes.
5. Run the narrowest meaningful verification before claiming success.
6. Leave the repository more consistent than you found it without expanding
   scope silently.

## Quality Bar

- Fix root causes, not symptoms.
- Do not ship code you cannot explain.
- Do not hide uncertainty. Mark unknowns and risks explicitly.
- Do not add abstractions until they remove real complexity, isolate an unstable
  boundary, or serve more than one real call site.
- Do not mix unrelated cleanup with feature work unless the cleanup is required
  for the feature.
- Prefer readable domain code over clever generic helpers.
- Do not manually edit generated files when an owning tool exists.

## Architecture Rules

- Keep feature behavior inside the owning module: `moderation/`, `channel/`,
  `assistant/`, `webapi/`, or `presentation/telegram/`.
- Keep route handlers, Telegram handlers, and UI handlers thin. They should
  orchestrate services, not duplicate business rules.
- Reuse the existing feature-based modular style. Do not introduce interface
  layers or entity-mapping layers unless there is a real second implementation
  or a concrete boundary to isolate.
- Cross-feature access should go through explicit services or repositories, not
  incidental imports that spread ownership.
- When a file becomes hard to review, split by responsibility before adding more
  behavior.

## Auth, Telegram, And Data Safety

- Treat the admin/public boundary in the web API as a security boundary.
- Public endpoints must be intentionally read-only and must not expose admin
  fields by accident.
- Admin mutations require authenticated admin sessions. Do not add auth bypass
  paths for convenience.
- Do not reuse production bot tokens, userbot sessions, or databases for a
  running development instance.
- The moderator bot uses HTML as its default parse mode. Any Telegram send/edit
  call that supplies `entities` or `caption_entities` must pass
  `parse_mode=None`.
- Telethon uses a real user session. Treat write operations, scheduled messages,
  and account-level side effects as higher-risk than ordinary bot API calls.
- Never log secrets, bot tokens, session strings, credentials, or sensitive
  payloads.

## Database And Deployment Rules

- Use PostgreSQL 18 as the supported database target.
- Schema changes require an Alembic migration, affected code/tests, and
  verification against PostgreSQL when behavior depends on PostgreSQL features.
- Do not run destructive database commands on shared environments without an
  explicit mitigation or rollback plan.
- Keep deployment reproducible: pin concrete action/image versions, avoid stale
  image tags, and preserve the `~/deploy/supervisor-telegram/` deployment model
  unless the user requests a redesign.
- CI/CD changes require syntax or configuration validation when practical.

## Testing And Verification

- For changed behavior, prefer a failing test first.
- For bug fixes, reproduce the symptom before editing when feasible.
- For refactors, prove behavior preservation with existing tests, type checks, or
  focused characterization tests.
- Use the narrowest lane that proves the change, then widen verification when
  the blast radius crosses module boundaries.
- Never claim "done", "fixed", or "clean" without fresh verification evidence.
- Follow `docs/testing/README.md` for unit, PostgreSQL integration, E2E, and web
  API test placement.

## Agent Workflow

- Manage context aggressively. Read only what is needed and summarize findings.
- Prefer reproducible command-line workflows over click-only instructions.
- Review generated diffs before committing.
- Do not commit agent plans, scratchpads, handoff notes, or execution logs as
  project documentation unless the user explicitly asks for that artifact.
- If a task is too risky because access, rollback, or ownership is unclear, stop
  and state the blocker.

## Git Discipline

- Work on a named branch for meaningful changes.
- Commit by concern when practical.
- Stage files explicitly and inspect `git status --short` before committing.
- Use non-destructive git commands by default.
- Do not amend, force-push, reset, or revert user work unless explicitly asked.

## Command Reference

Use the narrowest command that proves the change:

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
