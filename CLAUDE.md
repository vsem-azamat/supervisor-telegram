# CLAUDE.md

See [AGENTS.md](AGENTS.md) for the working contract and
[docs/invariants.md](docs/invariants.md) for rules the code cannot state itself.

## Quick Reference

```bash
# Run bot locally (also serves the MCP control plane when MCP_TOKEN is set)
uv run -m app.presentation.telegram

# Web API and web UI
uv run uvicorn app.webapi.main:app --host 127.0.0.1 --port 8787
pnpm --dir webui run dev

# Tests
uv run -m pytest                                        # all
uv run -m pytest tests/unit tests/handlers tests/middleware -x
uv run -m pytest --cov=app

# Quality
uv run ruff check app tests && uv run ruff format app tests
uv run ty check app tests
pnpm --dir webui run check

# Migrations
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

`docker compose up -d` is the production path and reads its configuration from
the deploying shell, not from a file on the host — deploy through the workflow
rather than running it by hand. See
[docs/deployment/](docs/deployment/).

Structure is not documented here on purpose — it drifts. Read `app/` directly.
