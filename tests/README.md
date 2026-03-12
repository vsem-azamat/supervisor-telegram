# Testing Guide

This document provides guidance for testing the moderator-bot project.

## Testing Strategy

### Test Pyramid

Our testing approach follows the test pyramid with:

- **Unit Tests (70%)** - Fast, isolated tests for individual components
- **Integration Tests (20%)** - Test interactions between components
- **End-to-End Tests (10%)** - Full workflow tests with FakeTelegramServer

### Test Categories

- **Unit Tests** (`tests/unit/`) - Test individual functions, classes, and methods
- **Integration Tests** (`tests/integration/`) - Test database operations and service integrations
- **End-to-End Tests** (`tests/e2e/`) - Test complete Telegram workflows with FakeTelegramServer
- **Handler Tests** (`tests/handlers/`) - Test Telegram handler functions with mocked dependencies
- **Middleware Tests** (`tests/middleware/`) - Test aiogram middleware behavior
- **Utility Tests** (`tests/utils/`) - Test shared utilities
- **Performance Tests** (`tests/performance/`) - Test performance and scalability

## Quick Start

### Running Tests

```bash
# Install dependencies
uv sync --dev

# Run all tests
uv run -m pytest

# Run specific test categories
uv run -m pytest tests/unit          # Unit tests only
uv run -m pytest tests/integration   # Integration tests only
uv run -m pytest tests/e2e           # End-to-end tests only
uv run -m pytest tests/handlers      # Handler tests only

# Run with coverage
uv run -m pytest --cov=app --cov-report=html

# Fast subset (unit + e2e, stop on first failure)
uv run -m pytest tests/unit tests/e2e -x
```

### Test Markers

```bash
uv run -m pytest -m unit           # Unit tests
uv run -m pytest -m integration    # Integration tests
uv run -m pytest -m e2e            # End-to-end tests
uv run -m pytest -m handlers       # Handler tests
uv run -m pytest -m "not slow"     # Exclude slow tests
```

## Test Structure

### Directory Layout

```
tests/
├── conftest.py                        # Shared fixtures (engine, session, repositories)
├── factories.py                       # Test data factories (UserFactory, ChatFactory, etc.)
├── fake_telegram.py                   # FakeTelegramServer (aiohttp Bot API simulator)
├── telegram_helpers.py                # TelegramObjectFactory, MockBot, utility functions
├── unit/                              # Unit tests
│   ├── test_domain_entities.py
│   ├── test_value_objects.py
│   ├── test_user_service.py
│   ├── test_application_services.py
│   ├── test_escalation_service.py
│   ├── test_channel_agent_v2.py
│   ├── test_channel_workflow.py
│   ├── test_generator.py
│   ├── test_orchestrator.py
│   ├── test_publisher.py
│   ├── test_review_agent.py
│   ├── test_review_service_helpers.py
│   ├── test_schedule_manager.py
│   ├── test_topic_splitter.py
│   ├── test_images.py
│   ├── test_ssrf.py
│   ├── test_spam_service.py
│   ├── test_assistant.py
│   ├── test_middlewares.py
│   ├── test_admin_middleware.py
│   ├── test_filters.py
│   ├── test_telethon_client.py
│   ├── test_tool_trace.py
│   └── test_domain_exceptions.py
├── integration/                       # Integration tests (DB + services)
│   ├── conftest.py                    # PostgreSQL testcontainers fixtures
│   ├── test_user_repository.py
│   ├── test_chat_repository.py
│   ├── test_pg_repository.py
│   ├── test_user_service_integration.py
│   └── test_assistant_conversation.py
├── e2e/                               # End-to-end tests (FakeTelegramServer)
│   ├── conftest.py                    # Shared e2e fixtures (db_engine, db_session_maker, fake_tg)
│   ├── test_agent_moderation.py
│   └── test_channel_review.py
├── handlers/                          # Handler unit tests
│   ├── test_moderation_handlers.py
│   ├── test_admin_handlers.py
│   ├── test_events_handlers.py
│   ├── test_blacklist_improvements.py
│   └── test_dependency_injection.py
├── middleware/                         # Middleware tests
│   └── test_blacklist_middleware.py
├── utils/                             # Utility tests
│   └── test_blacklist_utils.py
└── performance/                       # Performance tests
    └── test_repository_performance.py
```

### Key Fixtures

Available in all tests (from root `conftest.py`):

- `engine` - SQLite in-memory async engine
- `session` - Database session with savepoint isolation
- `user_repository` - User repository instance
- `chat_repository` - Chat repository instance
- `admin_repository` - Admin repository instance
- `sample_user_data` - Sample user data dictionary
- `sample_chat_data` - Sample chat data dictionary

Available in `tests/telegram_helpers.py` (auto-discovered by pytest):

- `telegram_factory` - `TelegramObjectFactory` instance
- `mock_bot` - `MockBot` instance

Available in `tests/e2e/conftest.py`:

- `db_engine` - SQLite in-memory engine for e2e tests
- `db_session_maker` - Async session maker for e2e tests
- `fake_tg` - `FakeTelegramServer` instance

## Test Factories

```python
from tests.factories import UserFactory, ChatFactory, AdminFactory

# Create single entities
user = UserFactory.create(username="testuser")
chat = ChatFactory.create_with_welcome("Welcome message")
admin = AdminFactory.create_inactive()

# Create batches
users = UserFactory.create_batch(10)
chats = ChatFactory.create_batch(5, is_forum=True)
```

## Test Infrastructure

### FakeTelegramServer

An aiohttp-based server that simulates the Telegram Bot API. Used in e2e tests to verify that the bot sends correct API requests without hitting real Telegram servers.

### SQLite In-Memory

Unit and e2e tests use SQLite in-memory databases for speed. Integration tests requiring PostgreSQL-specific features (pgvector, etc.) use testcontainers.

### Testcontainers

Integration tests in `tests/integration/conftest.py` use `testcontainers[postgres]` with the `pgvector/pgvector:pg18` image. Requires Docker access.

## Writing Tests

### Async Testing

All async tests are auto-detected by pytest-asyncio (configured in `pyproject.toml`):

```python
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

### Error Testing

```python
async def test_user_not_found_raises_exception(user_service):
    with pytest.raises(UserNotFoundException) as exc_info:
        await user_service.get_user_by_id(999999)
    assert exc_info.value.user_id == 999999
```

## Running in CI

Pre-commit hooks run ruff + mypy on commit, pytest on push.

```bash
# Quality checks
ruff check app tests && ruff format app tests
mypy app tests

# Full test suite
uv run -m pytest --cov=app
```
