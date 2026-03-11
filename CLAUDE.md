# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a modern Telegram bot for moderating educational chats in the Czech Republic. The bot provides comprehensive moderation features including muting, banning, blacklisting users, welcome messages, and message history tracking. Built with Python using aiogram for Telegram integration and follows a clean Domain-Driven Design (DDD) architecture with modern best practices.

## Technology Stack

### Backend
- **Python 3.12+** - Modern Python with full type hints
- **aiogram 3.x** - Async Telegram Bot API framework
- **SQLAlchemy 2.x** - Modern async ORM with declarative models
- **PostgreSQL 17.6** - Latest production database
- **Pydantic 2.x** - Data validation and settings management
- **structlog** - Structured logging
- **pytest** - Testing framework with async support
- **ruff** - Fast Python linter and formatter
- **uv 0.8.11** - Modern Python package manager

### Infrastructure
- **Docker** - Containerized development and deployment
- **PostgreSQL 17.6** - Latest stable database version
- **Adminer 5.3.0** - Modern database administration interface

## Development Setup

Dependencies are managed with `uv`. Set up the development environment:

```bash
# Create virtual environment and install dependencies
uv venv .venv
uv sync --dev
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Setup environment
cp .env.example .env
# Edit .env with your configuration
```

## Running the Application

### Development Mode
Run with Docker Compose (includes PostgreSQL, hot reload, and Adminer):
```bash
docker-compose -f docker-compose.dev.yaml up --build
```

This will start:
- **Bot service** - Telegram bot with hot reload
- **PostgreSQL** - Database server
- **Adminer** - Database administration UI on port 8080

### Production Mode
```bash
docker-compose up --build
```

### Local Development (without Docker)
```bash
# Make sure PostgreSQL is running and configured
uv run -m app.presentation.telegram
```

## Code Quality & Testing

### Run All Quality Checks
```bash
# Linting and formatting
ruff check app tests
ruff format app tests

# Type checking
mypy app tests

# Run tests
uv run -m pytest

# Run tests with coverage
uv run -m pytest --cov=app --cov-report=html
```

### Pre-commit Setup
```bash
# Install pre-commit hooks
uv run pre-commit install

# Run hooks manually
uv run pre-commit run --all-files
```

## Database Management

Uses Alembic for migrations with PostgreSQL in production and SQLite for testing.

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Downgrade
alembic downgrade -1
```

## Architecture (Domain-Driven Design)

The project follows clean DDD architecture with clear separation of concerns:

### Core Layers

- **`app/core/`** - Application core (config, logging, DI container)
- **`app/domain/`** - Pure domain logic (entities, value objects, repository interfaces, exceptions)
- **`app/application/`** - Application services and use cases
- **`app/infrastructure/`** - External concerns (database, external APIs)
- **`app/presentation/`** - User interface layer (Telegram handlers, middlewares)

### Domain Layer (`app/domain/`)

- **`entities.py`** - Rich domain entities with business logic
- **`value_objects.py`** - Immutable value objects (UserId, ChatId, etc.)
- **`repositories.py`** - Repository interfaces (ports)
- **`exceptions.py`** - Domain-specific exceptions
- **`models.py`** - SQLAlchemy ORM models (infrastructure concern)

### Key Design Patterns

- **Repository Pattern** - Abstracts data access with interfaces
- **Dependency Injection** - Managed through `app/core/container.py`
- **Value Objects** - Ensure data integrity and encapsulation
- **Domain Services** - Complex business logic that doesn't belong to entities
- **Structured Logging** - Contextual logging with structured data

### Configuration Management

Modern Pydantic-based configuration with environment variable support:

```python
from app.core.config import settings

# Access nested configuration
bot_token = settings.telegram.token
db_url = settings.database.url
log_level = settings.logging.level
```

### Dependency Injection

Services are managed through a lightweight DI container:

```python
from app.core.container import container

# Get repositories
user_repo = container.get(IUserRepository)
user_service = UserService(user_repo)
```

## Bot Commands

### Moderation Commands (Admins only)
- `/mute [minutes]` - Mute user (default 5 minutes)
- `/unmute` - Unmute user
- `/ban` - Ban user from chat and add to blacklist
- `/unban` - Remove from blacklist
- `black` - Add user to global blacklist (all chats)
- `/blacklist` - Show blacklisted users with unban buttons

### Configuration Commands
- `welcome [text]` - Configure welcome message
- `welcome -t [seconds]` - Set welcome message auto-delete time
- `/admin` - Add admin (reply to user)
- `/unadmin` - Remove admin (reply to user)

### Public Commands
- `/chats` - Show educational chat links
- `/start` - Bot introduction

## Testing Strategy

### Framework
- **pytest** with **pytest-asyncio** for async test support
- **SQLite in-memory** database for fast, isolated tests
- **Fixtures** provide clean test data and dependencies
- **Coverage reporting** with minimum 60% requirement

### Test Structure
```bash
tests/
├── conftest.py          # Shared fixtures and configuration
├── test_user_repository.py
├── test_chat_repository.py
├── test_admin_repository.py
└── unit/                # Unit tests
└── integration/         # Integration tests
```

### Running Tests
```bash
# All tests
uv run -m pytest

# Specific test types
uv run -m pytest -m unit
uv run -m pytest -m integration
uv run -m pytest -m "not slow"

# With coverage
uv run -m pytest --cov=app --cov-fail-under=60
```

## Logging

Structured logging with contextual information:

```python
from app.core.logging import BotLogger

logger = BotLogger("service_name")

# Log user actions
logger.log_user_action(user_id=123, action="user_blocked", chat_id=456)

# Log moderation actions
logger.log_moderation_action(
    admin_id=789,
    target_user_id=123,
    action="ban",
    chat_id=456,
    reason="spam"
)
```

## Environment Variables

See `.env.example` for all available configuration options. Key variables:

```bash
# Bot
BOT_TOKEN=your_bot_token_here
BOT_WEBHOOK_URL=
BOT_WEBHOOK_SECRET=
BOT_USE_WEBHOOK=false
ADMIN_SUPER_ADMINS=123456789,987654321
ADMIN_REPORT_CHAT_ID=

# Database
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_NAME=moderator_bot

# Application
DEBUG=false
ENVIRONMENT=development
TIMEZONE=UTC
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
LOG_FILE_PATH=logs/bot.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# Docker Configuration (for development)
ADMINER_PORT=8080
```

## Docker Development

The development setup includes:
- **Bot service** - Python bot with hot reload
- **PostgreSQL** - Database
- **Adminer** - Database administration UI (http://localhost:8080)
- **Hot reload** - Automatic restart on code changes
- **Volume mounts** - Live code editing

## Migration Guide

When migrating from older versions:

1. **Update dependencies**: `uv sync --dev`
2. **Update environment**: Copy new variables from `.env.example`
3. **Run migrations**: `alembic upgrade head`
4. **Update imports**: Domain entities are now in `app/domain/entities.py`
5. **Update tests**: Use new fixtures from `conftest.py`

## Performance Considerations

### Backend Optimization
- **Connection pooling** - Configured for production use with PostgreSQL
- **Async everywhere** - Fully async/await pattern throughout the application
- **Concurrent operations** - Batch operations for multiple chats and users
- **Structured logging** - Minimal performance impact with structured data
- **Type hints** - Full mypy compliance for better IDE support and runtime performance
- **Database indexing** - Optimized queries for large-scale chat management

### Development Experience
- **Hot reload** - Instant updates during development
- **Modern tooling** - Latest versions of all dependencies for best performance
- **Pre-commit hooks** - Automated code quality checks and formatting
- **Docker optimization** - Multi-stage builds and layer caching for faster deployments
