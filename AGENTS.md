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
- Production env example: `.env.prod.example` (copy to `.env` for production).
- Common commands:
  - Start dev stack: `docker compose up --build` (includes ngrok, hot-reload, adminer).
  - Start prod stack: `docker compose -f docker-compose.yaml up --build -d` (nginx exposed on `${NGINX_PORT:-8080}`).
  - Use production DB from dev: `docker compose --env-file .env.prod-db up` (optionally set `SKIP_MIGRATIONS=true`).
  - Run only core services: `docker compose up bot api nginx`.

## Production deployment

- Bot uses **polling mode** (not webhooks) - no special webhook endpoint needed.
- Requires **HTTPS** for Telegram WebApp - configure external reverse proxy (Nginx Proxy Manager, Caddy, Traefik, Cloudflare Tunnel).
- Set `WEBAPP_URL` to your HTTPS domain in `.env` (e.g., `https://bot.yourdomain.com`).
- External proxy should forward all traffic to `http://server-ip:${NGINX_PORT:-8080}` (internal nginx handles routing).
- No SSL certificates needed inside containers - handled by external proxy.
- Use `.env.prod.example` as template - has all required vars documented and optional vars commented out.
