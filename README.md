# Bot for moderating chats in Telegram

For moderating educational chats in the Czech Republic on Telegram.

## Links
- Bot: @konnekt_moder_bot
- One of the chats with the bot: @cvut_chat

## Features

| Feature | Description | Status |
|---------|-------------|--------|
| Moderating | Base commands for moderating the chat (mute, ban, etc.) | Done |
| Welcome message | Sending a welcome message to new chat members | Done |
| Saving messages history | Saving messages history to the database | Done |
| AI Report / Spam detection | `/report` and `/spam` trigger LLM agent to analyze and moderate | Done |
| Escalation | Agent escalates uncertain decisions to super admins via inline buttons | Done |
| Agent memory | Learns from admin overrides; uses user history and risk profile | Done |
| Web admin panel | React-based admin interface via Telegram WebApp | In progress |
| Captcha | Checking if the user is a bot on join | Planned |

## Architecture

Layered Domain-Driven Design:

- `app/domain` — domain models, entities, value objects, repository interfaces
- `app/infrastructure` — database, external APIs
- `app/application` — application services and use cases
- `app/presentation` — Telegram handlers, middlewares, web API
- `app/agent` — AI moderation agent (PydanticAI + OpenRouter)

## Setup and Run

### 1. Environment

```bash
cp .env.example .env
# Fill in BOT_TOKEN, DB_PASSWORD, ADMIN_SUPER_ADMINS at minimum
```

Key env vars for AI moderation:

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token (required) | — |
| `ADMIN_SUPER_ADMINS` | Comma-separated Telegram user IDs | — |
| `DB_USER` / `DB_PASSWORD` / `DB_NAME` | PostgreSQL credentials | `postgres` / — / `moderator_bot` |
| `AGENT_ENABLED` | Enable AI moderation agent | `false` |
| `AGENT_OPENROUTER_API_KEY` | OpenRouter API key for LLM | — |
| `AGENT_MODEL` | LLM model to use | `google/gemini-2.0-flash-001` |
| `AGENT_ESCALATION_TIMEOUT_MINUTES` | Escalation auto-resolve timeout | `30` |
| `AGENT_DEFAULT_TIMEOUT_ACTION` | Action on escalation timeout | `ignore` |

See `.env.example` for the full list.

### 2. Install dependencies

```bash
uv venv .venv
uv sync --dev
source .venv/bin/activate
```

### 3. Database

Apply migrations (requires running PostgreSQL):

```bash
alembic upgrade head
```

### 4. Run

#### Docker (recommended for development)

```bash
docker-compose -f docker-compose.dev.yaml up --build
```

Starts: bot (with hot reload), PostgreSQL, React webapp (port 3000), Adminer (port 8080).

#### Local (without Docker)

Make sure PostgreSQL is running and configured in `.env`, then:

```bash
uv run -m app.presentation.telegram
```

#### Production

```bash
docker-compose up --build
```

### Tests

```bash
uv run -m pytest              # all tests
uv run -m pytest --cov=app    # with coverage
```

### Linting

```bash
ruff check app tests
ruff format app tests
```

## Commands

### Moderation (admins)

| Command | Description |
|---------|-------------|
| `/mute [minutes]` | Mute user (default: 5 min). Reply to a message. |
| `/unmute` | Unmute user. Reply to a message. |
| `/ban` | Ban user and add to blacklist. Reply to a message. |
| `/unban` | Remove from blacklist. |
| `black` | Add user to global blacklist (all chats). Reply to a message. |
| `/blacklist` | Show blacklisted users with unban buttons. |
| `welcome [text]` | Set welcome message for new members. |
| `welcome -t [seconds]` | Set welcome message auto-delete time. |
| `/admin` | Add admin. Reply to a user. |
| `/unadmin` | Remove admin. Reply to a user. |

### AI Moderation (group chats)

| Command | Description |
|---------|-------------|
| `/report` | Report a message for AI analysis. Reply to the target message. |
| `/spam` | Report spam for AI analysis. Reply to the target message. |

The agent analyzes the message, considers user history and past admin corrections, then decides: ignore, warn, mute, ban, delete, blacklist, or escalate to a super admin.

### Public

| Command | Description |
|---------|-------------|
| `/chats` | Show educational chat links. |
| `/start` | Bot introduction. |
| `/webapp` | Open admin panel (super admins only). |
