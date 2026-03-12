# CLAUDE.md

Instructions for Claude Code when working on this repository.

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
mypy app tests

# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Architecture

Multi-agent Telegram platform: moderator bot + assistant bot + Telethon userbot.

### Layers (DDD)

```
app/
├── core/           # Config (Pydantic), logging, DI container
├── domain/         # Entities (dataclasses), value objects, repository interfaces, exceptions
├── application/    # Services (spam, history, users)
├── infrastructure/ # DB models (SQLAlchemy), repositories, Telethon client
├── presentation/   # Telegram handlers, middlewares
├── agent/          # AI moderation agent + channel content pipeline
│   ├── core.py         # PydanticAI moderation agent (Gemini Flash Lite)
│   ├── escalation.py   # HITL escalation with timeout
│   ├── memory.py       # Decision log + risk profiles
│   └── channel/        # Content pipeline
│       ├── workflow.py       # Burr state machine (9 actions)
│       ├── orchestrator.py   # Per-channel scheduling + orchestration
│       ├── generator.py      # LLM screening + post generation
│       ├── review_agent.py   # Conversational post editor
│       ├── semantic_dedup.py # pgvector cosine similarity
│       ├── feedback.py       # Admin preference summarization
│       ├── sources.py        # RSS + health tracking
│       └── http.py           # SSRF-protected HTTP client
└── assistant/      # Conversational admin bot
    ├── agent.py        # PydanticAI agent (Claude Sonnet 4.6), 30+ tools
    ├── bot.py          # Conversation management
    └── tools/          # channel, moderation, chat, telethon, dedup
```

### Key Files

- `app/core/config.py` — Pydantic settings hierarchy (6 nested config classes)
- `app/infrastructure/db/models.py` — 9 ORM models (including pgvector `Vector(768)` column)
- `app/domain/value_objects.py` — `PostStatus`, `EscalationStatus` StrEnums
- `app/core/text.py` — `escape_html()` utility
- `app/core/markdown.py` — `md_to_entities` / `md_to_entities_chunked` (telegramify-markdown)
- `app/core/time.py` — `utc_now()` helper for naive UTC datetimes
- `app/presentation/telegram/bot.py` — main entry, dispatcher setup
- `app/presentation/telegram/handlers/__init__.py` — router assembly, middleware wiring

### LLM Models (OpenRouter)

| Role | Model | Env var override |
|---|---|---|
| Screening | `google/gemini-2.0-flash-001` | `CHANNEL_SCREENING_MODEL` |
| Generation + review | `google/gemini-3.1-flash-lite-preview` | `CHANNEL_GENERATION_MODEL` |
| Moderation | `google/gemini-3.1-flash-lite-preview` | `AGENT_MODERATION_MODEL` |
| Assistant | `anthropic/claude-sonnet-4-6` | `AGENT_ASSISTANT_MODEL` |

## Important Patterns

### parse_mode=None with entities

The moderator bot uses `DefaultBotProperties(parse_mode="HTML")`. This **silently overrides** `entities`/`caption_entities` if `parse_mode=None` is not passed. All `send_photo`/`send_message`/`edit_message` calls using entities MUST include `parse_mode=None`.

### Markdown → Entities

Posts use Markdown (`**bold**`, `[link](url)`) converted via `md_to_entities` from `app/core/markdown.py`. Never send raw Markdown as HTML.

### Telethon Userbot

Authorized session file `moderator_userbot.session` (@work_azamat). Provides: chat history, search, member lists, scheduled messages (unavailable in Bot API).

### Content Pipeline Flow

`fetch_sources` → `split_and_enrich_topics` → `screen_content` → `generate_post` → `send_for_review` → **HITL halt** → `publish_post` / `handle_rejection`

Review agent supports multi-turn editing with per-post conversation memory (4h TTL, 200 LRU cap).

### Moderation Agent

Self-calibrating: injects last 5 admin corrections into system prompt. Escalates uncertain cases with inline buttons + timeout.

## Testing

- **700+ tests**, ~50s runtime
- Unit: SQLite in-memory
- Integration: testcontainers PostgreSQL
- E2E: `FakeTelegramServer` (aiohttp-based Bot API simulator)
- Pre-commit: ruff + mypy on commit, pytest on push

## Environment

See `.env.example` for all variables. Key ones:

```bash
BOT_TOKEN=                        # Moderator bot
ADMIN_SUPER_ADMINS=123,456        # Comma-separated user IDs
AGENT_OPENROUTER_API_KEY=         # OpenRouter for all LLM calls
AGENT_ENABLED=true                # Enable moderation agent
DB_USER= DB_PASSWORD= DB_NAME=   # PostgreSQL
```
