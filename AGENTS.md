# AGENTS instructions for moderator-bot

This file contains tips and reminders for Codex when working on this project.
Keep it up to date so future iterations of yourself can quickly understand how
the repository works.

## General guidelines

- Dependencies are managed with the `uv` tool. Set up the environment with:
  ```bash
  uv venv .venv
  uv sync --dev
  source .venv/bin/activate
  ```
- Run the quality checks before committing:
  ```bash
  ruff check tests
  uv run -m pytest -q
  ```
- When you introduce major changes (new packages, tools, or workflows), update
  this `AGENTS.md` with short notes explaining the change. This helps you get up
  to speed quickly the next time you work on the project.
- Keep the README synchronized with any setup or usage changes.
- Moderation commands now flow through `ModerationService`/`SpamService` injected by
  `DependenciesMiddleware`; avoid calling infrastructure repositories directly
  from handlers.

## Architecture overview

- The code base follows a layered Domain-Driven approach:
  - `app/domain` defines ORM models and entities.
  - `app/infrastructure` contains SQLAlchemy repositories and database helpers.
  - `app/application` implements business services.
  - `app/presentation` exposes the Telegram bot with routers and middlewares.
- The Docker configuration waits for the Postgres container with
  `scripts/wait_for_postgres.sh`, applies migrations via Alembic and then starts
  the bot.
- Tests run against an in-memory SQLite database via `pytest-asyncio` fixtures.

These notes should help future Codex sessions quickly understand the project
layout and any non-obvious logic.

## Docker Compose setup

- Base file: `docker-compose.yaml` (production-oriented defaults).
- Dev overrides: `docker-compose.override.yml` (auto-loaded by `docker compose`).
- Common commands:
  - Start dev stack: `docker compose up --build`.
  - Use production DB from dev: `docker compose --env-file .env.prod-db up` (optionally set `SKIP_MIGRATIONS=true`).
  - Run only core services: `docker compose up bot api nginx`.
