<h1 align="center">Supervisor Telegram</h1>

<p align="center">
  <em>AI-powered community management platform for Telegram</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/aiogram-3.x-blue?logo=telegram" alt="aiogram 3.x">
  <img src="https://img.shields.io/badge/PydanticAI-agents-purple" alt="PydanticAI">
  <img src="https://img.shields.io/badge/PostgreSQL-17-blue?logo=postgresql&logoColor=white" alt="PostgreSQL 17">
  <img src="https://img.shields.io/badge/pgvector-semantic_search-green" alt="pgvector">
  <img src="https://img.shields.io/badge/tests-700+-brightgreen" alt="Tests">
</p>

---

> **Alpha** — actively developed, core features working in production but APIs and architecture may change.

A multi-agent system that manages Telegram communities and automates content pipelines. Originally built for educational chat communities in the Czech Republic — now a general-purpose platform combining **mechanical moderation**, **AI-driven content generation**, and a **conversational admin interface**.

The system runs **three separate Telegram identities** working in concert: a rule-enforcing moderator bot, an LLM-powered assistant, and a Telethon userbot for Client API features unavailable to standard bots.

## System Architecture

```mermaid
graph TB
    subgraph Telegram["Telegram"]
        Users["👥 Community Members"]
        Admins["👮 Admins"]
        Channel["📢 Channel"]
        ReviewGroup["📝 Review Group"]
    end

    subgraph System["Supervisor Platform"]
        ModBot["🤖 Moderator Bot<br/><i>Mechanical commands</i><br/>/mute /ban /black /report"]
        Assistant["🧠 Assistant Bot<br/><i>Claude Sonnet 4.6</i><br/>30+ tools, conversational"]
        Userbot["👤 Telethon Userbot<br/><i>Client API access</i><br/>history, search, schedule"]
    end

    subgraph AI["AI Layer"]
        ModAgent["⚖️ Moderation Agent<br/><i>Gemini Flash Lite</i>"]
        Pipeline["📰 Content Pipeline<br/><i>Burr state machine</i>"]
        ReviewAgent["✏️ Review Agent<br/><i>Multi-turn editor</i>"]
    end

    subgraph Data["Data Layer"]
        PG[("PostgreSQL 17<br/>+ pgvector")]
        Sources["RSS / Brave / Perplexity"]
    end

    Users -->|messages| ModBot
    Users -->|/report /spam| ModBot
    Admins -->|natural language| Assistant
    ModBot -->|forwards reports| ModAgent
    ModAgent -->|escalates uncertain cases| Admins
    Assistant -->|manages| Pipeline
    Pipeline -->|fetches| Sources
    Pipeline -->|generates posts| ReviewGroup
    ReviewAgent -->|edits via conversation| ReviewGroup
    Admins -->|approve/reject| ReviewGroup
    Pipeline -->|publishes| Channel
    Userbot -->|schedules messages| Channel
    Assistant -->|delegates| Userbot
    ModBot --> PG
    Assistant --> PG
    Pipeline --> PG
```

## Agent Architecture

The platform uses **PydanticAI** agents with typed dependencies and structured outputs, all routed through **OpenRouter** to access different models at different cost/capability tiers.

```mermaid
graph LR
    subgraph Agents
        A1["🧠 Assistant Agent<br/>Claude Sonnet 4.6<br/><i>$3/$15 per 1M tokens</i>"]
        A2["⚖️ Moderation Agent<br/>Gemini Flash Lite<br/><i>$0.25/$1.50</i>"]
        A3["📰 Screening Agent<br/>Gemini 2.0 Flash<br/><i>$0.10/$0.40</i>"]
        A4["✏️ Generation Agent<br/>Gemini Flash Lite<br/><i>$0.25/$1.50</i>"]
        A5["🔍 Review Agent<br/>Gemini Flash Lite<br/><i>conversational</i>"]
    end

    subgraph Tools["30+ Tools"]
        T1["Channel Management<br/>add/remove channels,<br/>sources, schedules"]
        T2["Moderation<br/>mute, ban, blacklist,<br/>risk profiles"]
        T3["Content Intelligence<br/>semantic dedup,<br/>topic search, Brave"]
        T4["Telethon<br/>chat history, search,<br/>member lists"]
        T5["Post Editing<br/>get/update post,<br/>image search/replace"]
    end

    A1 --> T1
    A1 --> T2
    A1 --> T3
    A1 --> T4
    A5 --> T5
```

### Moderation Agent

The moderation agent receives reports and spam flags, gathers context through 4 information-gathering tools, and returns a typed `ModerationResult` with one of 7 possible actions.

**Self-calibrating**: Before each run, the 5 most recent admin override corrections are injected into the system prompt — the agent learns from where humans disagreed with it.

```mermaid
flowchart LR
    Report["🚩 /report or /spam"] --> Gather["Gather Context"]
    Gather --> History["User mod history"]
    Gather --> Risk["Risk profile<br/><i>cross-chat stats</i>"]
    Gather --> Recent["Recent chat actions"]
    Gather --> Corrections["Admin corrections"]
    History & Risk & Recent & Corrections --> Decide["LLM Decision"]
    Decide --> Actions{Action}
    Actions -->|confident| Execute["mute / ban / delete<br/>warn / blacklist / ignore"]
    Actions -->|uncertain| Escalate["⏱️ Escalate to Admin<br/><i>inline buttons + timeout</i>"]
    Escalate -->|admin responds| Execute
    Escalate -->|timeout| Default["Default action fires"]
```

### Content Pipeline

A **Burr state machine** orchestrates the full content lifecycle — from source fetching to publication — with a human-in-the-loop review step that halts execution until an admin approves.

```mermaid
flowchart TB
    subgraph Sources["Content Sources"]
        RSS["📡 RSS Feeds<br/><i>health-tracked,<br/>auto-disable on failure</i>"]
        Brave["🔍 Brave Search<br/><i>freshness-filtered</i>"]
        Sonar["🌐 Perplexity Sonar<br/><i>synthesized summaries</i>"]
    end

    Sources --> Fetch["fetch_sources"]
    Fetch --> Split["split_and_enrich_topics<br/><i>LLM splits multi-topic summaries</i>"]
    Split --> Dedup["Semantic Dedup<br/><i>pgvector cosine similarity</i><br/><i>threshold: 0.85</i>"]
    Dedup --> Screen["screen_content<br/><i>LLM relevance scoring 0–10</i><br/><i>batched JSON</i>"]
    Screen --> Feedback["Load Admin Feedback<br/><i>last 20 approve/reject<br/>summarized as preferences</i>"]
    Feedback --> Generate["generate_post<br/><i>LLM + image search</i><br/><i>900 char limit</i>"]
    Generate --> Review["send_for_review<br/><i>→ Review Group</i>"]
    Review --> HITL{"⏸️ HITL Halt"}
    HITL -->|"✅ Approve"| Publish["publish_post<br/><i>→ Channel</i>"]
    HITL -->|"✏️ Edit"| Agent["Review Agent<br/><i>multi-turn conversation</i>"]
    Agent --> HITL
    HITL -->|"❌ Reject"| Reject["handle_rejection<br/><i>feedback stored</i>"]
    HITL -->|"🔄 Regenerate"| Generate
    HITL -->|"📅 Schedule"| Schedule["Telethon scheduled message"]

    style HITL fill:#ffd700,stroke:#333,color:#000
```

**Feedback loop**: The pipeline learns from admin decisions. Before generating each post, it summarizes the last 20 approve/reject decisions into preference bullets and injects them into the generation prompt.

**Source discovery**: Periodically, Perplexity Sonar discovers new RSS feeds for each channel's topic. Each discovered URL is validated by actually fetching it and passes SSRF checks before being stored.

### Assistant Bot

A conversational interface where admins manage everything through natural language. The PydanticAI agent has access to **30+ tools** across 5 domains and maintains per-user conversation history with safe trimming that respects tool call boundaries.

```
Admin: "Run the pipeline for @my_channel"
{🔧 Channel status} ✓ — @my_channel: active
{🔧 Run pipeline} ✓

Pipeline started for @my_channel. 3 sources will be fetched,
screened, and sent to review.
```

```
Admin: "Ban user 123456 in all chats"
{🔧 User info} ✓ — User: @spammer, 47 messages across 3 chats
{🔧 Add to blacklist} ✓

User @spammer added to global blacklist.
Messages revoked in 3 chats.
```

## Key Features

| Area | What it does |
|---|---|
| **AI Moderation** | LLM-based message analysis with self-calibrating decisions, admin escalation with timeout, cross-chat risk profiles |
| **Content Pipeline** | Automated fetch → screen → generate → review → publish with Burr state machine and HITL |
| **Semantic Dedup** | pgvector embeddings prevent duplicate topics across a configurable time window |
| **Conversational Review** | Multi-turn post editing through natural language in a Telegram review group |
| **Admin Feedback Loop** | Generation learns from past approve/reject decisions |
| **Source Management** | RSS health tracking, auto-discovery via Perplexity Sonar, SSRF-protected validation |
| **Scheduled Publishing** | Telegram Client API (Telethon) for native scheduled messages |
| **Mechanical Moderation** | /mute, /ban, /blacklist, welcome messages, spam detection — no LLM overhead |
| **Cost Tracking** | Per-operation LLM cost breakdown with cache savings visibility |
| **700+ Tests** | Unit, integration, e2e with FakeTelegramServer and testcontainers |

## Tech Stack

| Layer | Technologies |
|---|---|
| **Bot Framework** | aiogram 3.x, Telethon (Client API) |
| **AI/Agents** | PydanticAI, OpenRouter (Claude Sonnet, Gemini Flash, Perplexity Sonar) |
| **State Machine** | Burr (checkpointable HITL workflow) |
| **Database** | PostgreSQL 17 + pgvector, SQLAlchemy 2.x async, Alembic |
| **Search** | Brave Search API (web + images), Perplexity Sonar (synthesis) |
| **Architecture** | DDD (domain/application/infrastructure/presentation), dependency injection |
| **Quality** | ruff, mypy (strict), pytest, pre-commit, structlog |
| **Infrastructure** | Docker multi-stage, uv package manager |

## Project Structure

```
app/
├── agent/                  # AI agents
│   ├── channel/            # Content pipeline
│   │   ├── workflow.py     # Burr state machine (9 actions)
│   │   ├── orchestrator.py # Per-channel orchestration + scheduling
│   │   ├── generator.py    # LLM screening + post generation
│   │   ├── review_agent.py # Conversational post editor
│   │   ├── semantic_dedup.py
│   │   ├── feedback.py     # Admin preference summarization
│   │   ├── sources.py      # RSS fetching + health tracking
│   │   └── http.py         # SSRF-protected HTTP client
│   ├── core.py             # Moderation agent
│   ├── escalation.py       # HITL escalation with timeout
│   └── memory.py           # Decision log + risk profiles
├── assistant/              # Conversational admin bot
│   ├── agent.py            # PydanticAI agent (Claude Sonnet)
│   ├── bot.py              # Conversation management
│   └── tools/              # 30+ tools across 5 modules
├── core/                   # Config, logging, DI
├── domain/                 # Entities, value objects, interfaces
├── application/            # Services (spam, history, users)
├── infrastructure/         # DB models, repositories, Telethon
└── presentation/           # Telegram handlers, middlewares
```

## Quick Start

```bash
# Clone and configure
git clone https://github.com/vsem-azamat/supervisor-telegram.git
cd supervisor-telegram
cp .env.example .env  # fill in BOT_TOKEN, DB_*, AGENT_OPENROUTER_API_KEY

# Development (Docker)
docker compose -f docker-compose.dev.yaml up --build

# Or local
uv sync --dev
uv run alembic upgrade head
uv run -m app.presentation.telegram
```

## Security

- **SSRF protection** — async DNS validation on all LLM-returned URLs before fetching (14 dedicated tests)
- **Prompt injection defense** — external content sandboxed in XML boundary tags, boundary markers escaped in sanitizer
- **Global blacklist middleware** — TTL-cached, auto-bans across all managed chats
- **Escalation timeouts** — uncertain AI decisions auto-resolve, never left hanging

## License

MIT
