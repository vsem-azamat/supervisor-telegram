# Moderator-bot — Autonomous Ecosystem Tracker

> Single source of truth for goals, tasks, research, decisions, and current status.
> Update this file as work progresses. Keep entries short and actionable.

## 0) Global vision (high-level)

We operate multiple Telegram **chats and channels** for CIS students in Czechia (CVUT, UK, VSE, VUT, MUNI, VSCHT, etc.).
Goal: an **autonomous ecosystem** that can:

- Moderate chats (today's scope)
- Autonomously run channels: find resources/topics, produce posts, schedule, adapt
- Communicate with Azamat: ask for approvals early, escalate important questions
- Orchestrate chats/channels metadata: descriptions, pins, rules, titles, etc.
- Learn from admin feedback: summarize preferences, drop bad sources, improve generations
- Potentially use Telegram Client API (Pyrogram) for advanced actions (ads outreach, richer automation)

Constraints:
- Minimize cost (model/tool usage efficiency matters)
- Architecture can evolve
- No artificial limits on tools (we can integrate what we need)

## 1) Current branch / scope

- Repo: `moderator-bot`
- Branch: `claude/telegram-chat-bot-JfIPd`
- Objective: **Channel content agent with review workflow** — autonomous content pipeline with admin approval via private review channel

### Current Goal: Channel Agent v2 — Review Flow

Agent autonomously discovers content, generates posts, sends to private review channel with inline buttons. Admin reviews, edits via chat conversation with agent, approves/rejects. Agent learns from feedback.

**Key requirements:**
1. NO hardcoded RSS feeds — agent discovers sources via Perplexity Sonar
2. Posts go to private review channel (not directly to main channel)
3. Inline buttons under each draft: Approve / Reject / Regen / Shorter / Longer / Translate
4. Linked discussion chat: admin replies with feedback, agent modifies post
5. Agent summarizes admin feedback + source stats to improve over time
6. Auto-disable bad RSS sources based on health tracking

### Definition of Done (Channel Agent v2)
- [x] Review channel flow: draft -> buttons -> approve -> publish to main channel
- [x] Inline keyboard with actionable buttons (approve, reject, regen, shorter, longer, translate)
- [x] Reply-based editing: admin writes feedback in discussion chat, agent updates draft
- [x] Source discovery agent: finds RSS feeds via Perplexity, validates, adds to DB
- [x] Admin feedback memory: agent summarizes preferences to improve future posts
- [x] Source health: auto-disable broken feeds, relevance scoring from admin actions
- [x] Unit tests for review handler, source discovery, feedback system (66 tests)
- [x] RSS sources from .env deprecated — agent manages sources autonomously
- [x] Alembic migration for v2 schema changes
- [ ] Create private review channel + linked discussion chat in Telegram
- [ ] End-to-end test: deploy and verify full review flow works

## 2) Task board

### Done
- [x] Wire `events` router (chat_member handlers were dead code) — `c30a961`
- [x] Make `agent_core` optional when agent disabled — `c30a961`
- [x] `allowed_updates` filter + admin cache TTL — `65eec30`
- [x] E2E test infrastructure: FakeTelegramServer + 9 tests — `9c3d80d`
- [x] DDD fix: ORM models from domain to infrastructure — `c168308`
- [x] testcontainers[postgres] + 6 PG integration tests
- [x] Pre-commit hooks (ruff, mypy, pytest, eslint/tsc)
- [x] All code quality: ruff 0, mypy 0, 351 tests
- [x] Channel agent v1: RSS fetch -> LLM screen -> generate -> publish — `f56bc72`
- [x] Perplexity Sonar discovery + DB-backed source management — `3057497`
- [x] Successfully published 3 posts to @test908070 (msg IDs 44-46)

### Done (v2)
- [x] Channel agent v2: review flow with inline buttons + discussion chat editing — `9b1fcf0`
- [x] Source discovery agent: auto-find RSS feeds via Perplexity Sonar
- [x] Admin feedback memory: summarizes preferences, wired into generation pipeline
- [x] Source relevance scoring: approve boosts, reject penalizes, auto-disables low-quality
- [x] Alembic migration for v2 columns (channel_posts + channel_sources)

### Done (v2.1 — security, perf, features)
- [x] Super admin auth on review callbacks + reply handlers — `cf04abf`
- [x] Performance: async RSS fetching (gather+semaphore), feedparser in executor, N+1 fix
- [x] Multi-channel orchestration with per-channel configs and posting schedules
- [x] LLM cost tracking with structured logging (`cost_tracker.py`)
- [x] REST API with magic link auth for stats (no Telegram WebApp dependency)
- [x] Score parsing bugfix (8.5 no longer parsed as 85)
- [x] Memory leak fix: cap _seen_ids at 10k with LRU eviction
- [x] HTML stripping on RSS content before LLM processing
- [x] E2E tests for channel review flow (8 tests)
- [x] API unit tests
- [x] 401 tests passing, all quality checks green

### Done (v2.2 — Burr, Telethon, research)
- [x] Research: 8 docs on multi-agent architectures, memory, content automation, observability, Telegram ecosystem, framework comparisons
- [x] Code reviews: security, architecture, channel agent quality — 3 review docs
- [x] Security fixes: HTML injection (escape_html), prompt injection (XML delimiters), secret validation, race conditions
- [x] Burr state machine: 7-action content pipeline with HITL halt/resume, fallback to legacy on error
- [x] Telethon Client API: authorized work account (@work_azamat), wrapper with flood wait handling, 6 methods tested against real API
- [x] Dependency upgrades: aiogram 3.26, pydantic 2.12.5, sqlalchemy 2.0.48, ruff 0.15.5, burr 0.40.2, telethon 1.42+
- [x] Pre-commit hooks fixed: ruff 0.15.5, pytest skips PG integration tests
- [x] 411 tests passing, all quality checks green

### Done (v2.3 — Review infrastructure)
- [x] Created "Konnekt Review" supergroup (-1003823967369) via Telethon
- [x] Bot @konnekt_moder_bot added as admin with posting rights
- [x] Azamat (268388996) added as admin (required for ManagedChatsMiddleware)
- [x] CHANNEL_REVIEW_CHAT_ID configured in .env
- [x] Bot verified: can send messages to review group
- [x] Telethon client: added create_supergroup, add_chat_admin, invite_to_chat, send_message methods
- [x] Setup script: scripts/setup_review_channel.py
- [x] Key finding: ManagedChatsMiddleware makes bot leave_chat if no super_admin is admin in group

### Done (v2.4 — Live pipeline test, model upgrade, DB fixes)
- [x] Full content pipeline tested against real Telegram (RSS -> screen -> generate -> review)
- [x] Two posts successfully sent to "Konnekt Review" with inline buttons
- [x] Gemini 3.1 models: screening/generation = gemini-3.1-flash-lite-preview, agent = gemini-3.1-pro-preview
- [x] Fixed datetime timezone mismatch (naive vs aware) for PostgreSQL TIMESTAMP columns
- [x] Alembic migration applied: channel_posts review columns + source relevance_score
- [x] 461 tests passing (50 new: 14 escalation, 22 orchestrator, 14 telethon)

### Done (v2.5 — Code quality refactor)
- [x] Extracted `openrouter_chat_completion()` into `app/agent/channel/llm_client.py` (replaced 4 duplicated HTTP patterns)
- [x] Created `app/core/time.py` with `utc_now()` helper (replaced 15+ inline datetime calls)
- [x] Centralized `LANGUAGE_NAMES` + `language_name()` in channel config
- [x] Added `http_timeout`, `screening_threshold`, `temperature` to `ChannelAgentSettings`
- [x] Added `openrouter_base_url` to `AgentSettings`
- [x] Added `_MAX_API_PAGE_SIZE`, `_BLACKLIST_PAGE_SIZE` constants
- [x] Deduplicated RSS feed parsing into `_parse_feed_entries()` helper
- [x] Fixed moderation logging (stdlib logger %-style, not structlog kwargs)
- [x] Fixed hardcoded timezone to use `settings.timezone`
- [x] Added Gemini 3.1 model pricing to cost_tracker
- [x] 461 tests passing, all quality checks green

### Done (v3.0 — Brand identity, images, content style)
- [x] Competitor analysis: @the_cesko, @pozor_brno, @czech_info — content style, footers, engagement patterns
- [x] Brand style guide: `docs/content-style-guide.md` — Konnekt tone, footer, formatting rules
- [x] Updated GENERATION_PROMPT with Konnekt brand style (footer, tone, no hashtags)
- [x] Image system: `app/agent/channel/images.py` — OG image extraction, RSS media tags, HTML img fallback
- [x] RSS media extraction: `extract_rss_media_url()` for media:content, media:thumbnail, enclosures
- [x] `image_url` field added to ContentItem, GeneratedPost, ChannelPost model
- [x] Publisher updated: sends photo+caption (<=1024 chars) or photo+text reply (>1024)
- [x] Review flow updated: sends photo with review buttons
- [x] Approve flow updated: publishes with photo via centralized publisher
- [x] Alembic migration: `image_url` column on channel_posts
- [x] 8 test posts published to @test908070 (5 text-only + 3 with photos from RSS/OG images)
- [x] Working RSS feeds identified: ct24.cz (with images), irozhlas.cz (with images), novinky.cz, seznamzpravy.cz, blesk.cz
- [x] 500 tests passing, all quality checks green

### Done (v3.1 — 1 news = 1 post, multi-image, deployment)
- [x] GENERATION_PROMPT: enforce single news per post, max 900 chars (fits photo caption)
- [x] Multi-image publisher: media group/album support with graceful fallback chain
- [x] Smart image filtering: skip thumbnails (width<400), deduplicate by base URL, max 3 images
- [x] `image_urls` JSON column on ChannelPost + Alembic migration
- [x] Orchestrator + workflow: generate one post per relevant item (not 3 combined)
- [x] @konnekt_channel created (https://t.me/konnekt_channel) with bot + Azamat as admins
- [x] 5 RSS sources added to DB: CT24, iROZHLAS, Novinky, Seznam Zpravy, Blesk
- [x] E2E review flow verified: fetch -> screen -> generate -> review -> approve -> publish
- [x] 3 test posts published with proper format (443-589 chars, photo+caption, Konnekt footer)
- [x] Deployed in test mode: @test908070 channel, -1003823967369 review group
- [x] 500 tests passing, all quality checks green

### ON HOLD
- [ ] DDD repository refactor — patch at `docs/ddd-refactor.patch`

### Backlog
- [ ] Multi-agent hierarchy (Coordinator + Moderation/Content/Orchestration/Analytics)
- [ ] Approval workflow: generalized escalation with multi-approver
- [ ] Analytics agent (scheduled reports)

## 3) Architecture: Channel Agent v2

```
Source Discovery Agent (daily)
  Perplexity: "find RSS feeds about..."
  -> validate (fetch + check items)
  -> add to DB (channel_sources)
  -> auto-disable broken sources

Content Pipeline (every N minutes)
  1. Fetch DB sources + Perplexity discovery
  2. Screen items (Gemini Flash, score 0-10)
  3. Generate post (Gemini Flash, HTML)
  4. Send to Review Channel with inline buttons

Review Channel (@private)
  [Draft post text]
  [Approve] [Reject] [Regen] [Shorter] [Longer] [Translate]

  Discussion Chat (linked):
    Admin: "add deadline info"
    Agent: *updates post* "Done, updated version above"
    Admin: *clicks Approve*

Main Channel (@test908070 test / @konnekt_channel prod)
  Published post (photo + caption, 1 news = 1 post)

Feedback Memory:
  Agent summarizes: which sources admin likes, what edits are common,
  which topics get approved vs rejected -> uses this to improve
```

## 4) Decisions log (ADR-lite)

- 2026-03-06: RSS sources NOT in .env — agent discovers them autonomously via Perplexity
- 2026-03-06: All posts go through review channel first — no direct publishing
- 2026-03-06: Review channel has linked discussion chat for back-and-forth with agent
- 2026-03-06: Agent summarizes admin feedback to improve source selection and post quality
- 2026-03-05: Approval policy — sensitive actions always require explicit approval
- 2026-03-06: Client API — Telethon (not Pyrogram), authorized work account with session file
- 2026-03-06: Burr chosen over LangGraph — lightweight async state machine, Apache Incubating, no legacy baggage
- 2026-03-06: pgvector preferred over Qdrant at our scale (< 1M vectors, already have PostgreSQL)
- 2026-03-06: Gemini 3.1 models: agent=gemini-3.1-pro-preview, screening/generation=gemini-3.1-flash-lite-preview
- 2026-03-06: Code quality refactor: eliminate 15 categories of magic values, centralize config, DRY
- 2026-03-05: Client API — separate Pyrogram service account (superseded by Telethon)
- 2026-03-05: `allowed_updates` — message, callback_query, chat_member only
- 2026-03-05: Admin cache TTL = 5 min

## 5) Open questions for Azamat

- Q1 (resolved): Posts require approval -> Yes, always via review channel
- Q2 (resolved): RSS sources approach -> Agent discovers autonomously, no .env hardcoding
- Q3: Create private review channel with linked discussion chat — needed for v2
- Q4: Confirm bot has admin rights in test chat

## 6) Status updates (chronological)

- 2026-03-05: Agent pipeline end-to-end confirmed. 4 fixes applied. E2E tests built. DDD refactor.
- 2026-03-06: PG integration tests. Pre-commit hooks. All quality checks pass (285 tests).
- 2026-03-06: Channel agent v1 built and deployed. RSS + Perplexity discovery pipeline. 3 posts published to @test908070. Perplexity Sonar found excellent content (scholarships scoring 10/10).
- 2026-03-06: Starting v2 — review flow with inline buttons, discussion chat editing, source discovery agent, admin feedback memory.
- 2026-03-06: v2 code complete — review flow, feedback memory wired into generation, source relevance scoring, alembic migration. 351 tests (66 channel agent v2). All quality checks pass.
- 2026-03-06: v2.1 — security fixes (auth on review callbacks), performance (async RSS, executor, N+1), multi-channel orchestration, cost tracking, REST API with magic link auth. 401 tests. All checks pass.
- 2026-03-06: v2.2 — Burr workflow, Telethon integration, security fixes (HTML/prompt injection), 8 research docs, 3 code reviews, dependency upgrades. 411 tests.
- 2026-03-06: Telethon Client API authorized and tested: get_user_info, get_chat_info, get_chat_history, get_chat_members, search_messages, forward_messages — all working against real Telegram.
- 2026-03-06: Available test resources: FFGroup (-4650848481), Konnekt Dev (-1002287191880, @test908070), Bot (5145935834), Azamat (268388996).
- 2026-03-06: Review infrastructure created: "Konnekt Review" (-1003823967369), bot + Azamat as admins. Key lesson: ManagedChatsMiddleware requires super_admin to be admin in group, otherwise bot auto-leaves.
- 2026-03-06: v2.5 — Code quality refactor: extracted LLM client, centralized config/constants/datetime, deduplicated RSS parsing, fixed logging. 461 tests. All checks pass.
- 2026-03-06: v3.0 — Brand identity + image system. Analyzed 3 competitor channels. Created Konnekt style guide with distinctive footer. Built image pipeline (OG image, RSS media, HTML img fallback). 8 posts published to @test908070 (5 text + 3 with photos). Updated generation prompt, publisher, review flow. 500 tests. All checks pass.
- 2026-03-06: v3.1 — 1 news = 1 post (no more cramming). Multi-image albums. Smart image filtering (width>=400, dedup by base URL). @konnekt_channel created. 5 RSS sources in DB. Full E2E review flow verified. Deployed in test mode.
