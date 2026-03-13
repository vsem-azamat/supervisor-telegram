# Architecture

> Last updated: 2026-03-13

## Design Philosophy

**Feature-based modular architecture** — not pure DDD, not flat scripts. Each feature module groups its own models, services, and handlers. Shared infrastructure (DB, config, logging) lives in `core/` and `infrastructure/`. ORM models serve as the single data representation — no entity/model mapping layer.

Key principles:
- **ORM models are the domain models** where there's a single data source (which is most of the codebase)
- **No abstract interfaces** unless there are multiple implementations
- **Feature modules** (`moderation/`, `agent/channel/`, `assistant/`) own their vertical slice
- **No backward-compat shims** — all migrations complete, no legacy re-export files

## Module Map

```
app/
├── core/                          # Shared foundation
│   ├── config.py                  # Pydantic settings hierarchy (9 classes)
│   ├── container.py               # Service locator / DI container
│   ├── enums.py                   # PostStatus, EscalationStatus, ReviewDecision
│   ├── exceptions.py              # DomainError, UserNotFoundException
│   ├── logging.py                 # structlog setup
│   ├── markdown.py                # Markdown → MessageEntity conversion
│   ├── text.py                    # escape_html()
│   └── time.py                    # utc_now() helper
│
├── moderation/                    # AI moderation feature module
│   ├── agent.py                   # PydanticAI moderation agent (Gemini Flash Lite)
│   ├── blacklist.py               # Global blacklist add/remove across all chats
│   ├── escalation.py              # HITL escalation with configurable timeout
│   ├── memory.py                  # Decision log + cross-chat risk profiles
│   ├── report.py                  # Report forwarding to moderators
│   ├── spam_service.py            # Spam detection service
│   ├── user_service.py            # User block/unblock, verification
│   └── history_service.py         # Message history tracking
│
├── agent/                         # AI agent infrastructure
│   ├── prompts.py                 # Shared prompt templates
│   ├── schemas.py                 # Shared Pydantic schemas (ModerationResult, etc.)
│   ├── tool_trace.py              # Tool call tracing for assistant
│   └── channel/                   # Content pipeline feature module
│       ├── config.py              # ChannelAgentSettings
│       ├── orchestrator.py        # Per-channel scheduling + lifecycle
│       ├── workflow.py            # Burr state machine (9 actions)
│       ├── generator.py           # LLM screening + post generation
│       ├── sources.py             # RSS fetching + health tracking
│       ├── source_discovery.py    # Perplexity-based feed discovery
│       ├── source_manager.py      # Source CRUD operations
│       ├── semantic_dedup.py      # pgvector cosine similarity dedup
│       ├── feedback.py            # Admin preference summarization
│       ├── publisher.py           # Post publishing logic
│       ├── schedule_manager.py    # Telethon scheduled messages
│       ├── embeddings.py          # OpenAI-compatible embedding client
│       ├── llm_client.py          # Centralized OpenRouter HTTP client
│       ├── http.py                # SSRF-protected HTTP fetching
│       ├── sanitize.py            # Prompt injection sanitizer
│       ├── brave_search.py        # Brave Search API wrapper
│       ├── images.py              # Image search + download
│       ├── cost_tracker.py        # LLM cost tracking
│       ├── topic_splitter.py      # Multi-topic splitting
│       ├── channel_repo.py        # Channel DB operations
│       ├── discovery.py           # Source discovery helpers
│       ├── exceptions.py          # Channel-specific exceptions
│       └── review/                # Review submodule
│           ├── agent.py           # Conversational review agent (multi-turn)
│           ├── presentation.py    # Review message UI (keyboards, send/edit)
│           └── service.py         # Review business logic (approve/reject/edit)
│
├── assistant/                     # Conversational admin bot
│   ├── agent.py                   # PydanticAI agent (Claude Sonnet 4.6)
│   ├── bot.py                     # Conversation management, dispatcher
│   └── tools/                     # 30+ tools across 5 domains
│       ├── channel.py             # Channel/source/schedule management
│       ├── moderation.py          # Mute, ban, blacklist, user info
│       ├── agent_moderation.py    # AI moderation analysis tools
│       ├── chat.py                # Chat settings, welcome messages
│       ├── dedup.py               # Semantic dedup + Brave search
│       └── telethon.py            # Chat history, search, members
│
├── infrastructure/                # External system adapters
│   ├── db/
│   │   ├── models.py              # 9 SQLAlchemy ORM models (+ pgvector)
│   │   ├── repositories/          # 5 repository classes (no interfaces)
│   │   ├── base.py                # Declarative base
│   │   └── session.py             # Async session factory
│   └── telegram/
│       └── telethon_client.py     # Telethon userbot client
│
├── presentation/                  # Telegram bot handlers
│   └── telegram/
│       ├── bot.py                 # Main entry point, dispatcher setup
│       ├── handlers/              # Command/callback handlers (7 routers)
│       ├── middlewares/           # 6 middlewares (auth, history, deps, etc.)
│       └── utils/                 # Filters, callback data, buttons, blacklist utils
```

## Configuration Hierarchy

All settings are Pydantic `BaseSettings` classes, loaded from `.env`:

```
AppSettings                        # APP_DEBUG, APP_ENVIRONMENT
├── database: DatabaseSettings     # DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
├── telegram: TelegramSettings     # BOT_TOKEN
├── admin: AdminSettings           # ADMIN_SUPER_ADMINS, ADMIN_REPORT_CHAT_ID
├── logging: LoggingSettings       # LOG_LEVEL, LOG_FILE_PATH
├── openrouter: OpenRouterSettings # OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_BRAVE_API_KEY
├── moderation: ModerationSettings # MODERATION_MODEL, MODERATION_ENABLED, MODERATION_ESCALATION_TIMEOUT_MINUTES
├── assistant: AssistantSettings   # ASSISTANT_BOT_TOKEN, ASSISTANT_BOT_ENABLED, ASSISTANT_BOT_MODEL
├── telethon: TelethonSettings     # TELETHON_API_ID, TELETHON_API_HASH, TELETHON_ENABLED
└── channel: ChannelAgentSettings  # CHANNEL_ENABLED, CHANNEL_GENERATION_MODEL, ... (lazy-loaded)
```

Global singleton: `from app.core.config import settings`

## LLM Models (via OpenRouter)

| Role | Model | Cost (per 1M tokens) | Config path |
|---|---|---|---|
| Screening | `google/gemini-2.0-flash-001` | $0.10 / $0.40 | `settings.channel.screening_model` |
| Generation + review | `google/gemini-3.1-flash-lite-preview` | $0.25 / $1.50 | `settings.channel.generation_model` |
| Moderation | `google/gemini-3.1-flash-lite-preview` | $0.25 / $1.50 | `settings.moderation.model` |
| Assistant | `anthropic/claude-sonnet-4-6` | $3.00 / $15.00 | `settings.assistant.model` |

## Data Flow

### Three-Bot Model

```
Moderator Bot (@konnekt_moder_bot)
├── Mechanical commands: /mute, /ban, /black, /report
├── Welcome messages, captcha
├── Publishes posts to channels
└── Default parse_mode="HTML" — MUST pass parse_mode=None with entities

Assistant Bot (@dasdjkalsdj_bot)
├── LLM-powered: PydanticAI agent with 30+ tools
├── Sends review messages to review group
├── Handles review callbacks (approve/reject/edit)
└── No default parse_mode — entities work without override

Telethon Userbot (@work_azamat)
├── Client API features unavailable to bots
├── Chat history, search, member lists
└── Scheduled message publishing
```

### Content Pipeline

```
fetch_sources → split_and_enrich_topics → screen_content → generate_post
    → send_for_review → [HITL halt] → publish_post / handle_rejection
```

Orchestrated by Burr state machine with checkpoint/resume. Review agent supports multi-turn editing with per-post conversation memory (4h TTL, 200 LRU cap).

### Moderation Flow

```
/report or /spam → Agent gathers context (history, risk profile, corrections)
    → LLM decision → confident: execute / uncertain: escalate with timeout
```

Self-calibrating: injects last 5 admin corrections into system prompt.

## Key Patterns

### Repositories

Concrete classes, no abstract interfaces. Return ORM models directly. Located in `app/infrastructure/db/repositories/`. Created via Container factory methods.

### Container

Service locator pattern in `app/core/container.py`. Provides:
- `get_session()` — async DB session
- `get_bot()` / `try_get_bot()` — moderator bot instance
- `get_*_repository(session)` — repository factories
- `get_channel_orchestrator()` — channel pipeline orchestrator
- `get_telethon_client()` — Telethon userbot

### Enums

All shared enums in `app/core/enums.py`: `PostStatus`, `EscalationStatus`, `ReviewDecision`.

## Testing

- **600+ tests**, ~20s runtime
- **Unit**: SQLite in-memory, mocked dependencies
- **Integration**: testcontainers PostgreSQL (real DB)
- **E2E**: `FakeTelegramServer` (aiohttp-based Bot API simulator)
- **Pre-commit**: ruff + ty on commit, pytest on push
- **Factories**: `tests/factories.py` — ORM model factories (User, Chat, Admin, Message, ChatLink)
