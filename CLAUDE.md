# CLAUDE.md

See [AGENTS.md](AGENTS.md) for the working contract and
[docs/invariants.md](docs/invariants.md) for rules the code cannot state itself.

## Quick Reference

```bash
# Run bot locally (also serves the MCP control plane when MCP_ENABLED)
uv run -m app.presentation.telegram

# Run with Docker (production image)
docker compose up -d

# Tests
uv run -m pytest                                        # all
uv run -m pytest tests/unit tests/handlers tests/middleware -x
uv run -m pytest --cov=app

# Quality
ruff check app tests && ruff format app tests
ty check app tests

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Structure is not documented here on purpose — it drifts. Read `app/` directly.
