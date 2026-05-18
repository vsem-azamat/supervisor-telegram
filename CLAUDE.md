# CLAUDE.md

See [AGENTS.md](AGENTS.md) for repository instructions.

## Quick Reference

```bash
# Run bot locally
uv run -m app.presentation.telegram

# Run with Docker (production image)
docker compose up -d

# Tests
uv run -m pytest                          # all tests
uv run -m pytest tests/unit tests/e2e -x  # fast subset
uv run -m pytest --cov=app                # with coverage

# Quality
ruff check app tests && ruff format app tests
ty check app tests

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Use the canonical docs instead of duplicating repository guidance here:

- [Documentation hub](docs/README.md)
- [Architecture](docs/architecture.md)
- [Domain rules](docs/domain/README.md)
- [Testing strategy](docs/testing/README.md)
