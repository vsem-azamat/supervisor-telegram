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
- [ ] Review channel flow: draft -> buttons -> approve -> publish to main channel
- [ ] Inline keyboard with actionable buttons (approve, reject, regen, shorter, longer, translate)
- [ ] Reply-based editing: admin writes feedback in discussion chat, agent updates draft
- [ ] Source discovery agent: finds RSS feeds via Perplexity, validates, adds to DB
- [ ] Admin feedback memory: agent summarizes preferences to improve future posts
- [ ] Source health: auto-disable broken feeds, relevance scoring from admin actions
- [ ] Unit tests for review handler, source discovery, feedback system
- [ ] RSS sources from .env deprecated — agent manages sources autonomously

## 2) Task board

### Done
- [x] Wire `events` router (chat_member handlers were dead code) — `c30a961`
- [x] Make `agent_core` optional when agent disabled — `c30a961`
- [x] `allowed_updates` filter + admin cache TTL — `65eec30`
- [x] E2E test infrastructure: FakeTelegramServer + 9 tests — `9c3d80d`
- [x] DDD fix: ORM models from domain to infrastructure — `c168308`
- [x] testcontainers[postgres] + 6 PG integration tests
- [x] Pre-commit hooks (ruff, mypy, pytest, eslint/tsc)
- [x] All code quality: ruff 0, mypy 0, 285 tests
- [x] Channel agent v1: RSS fetch -> LLM screen -> generate -> publish — `f56bc72`
- [x] Perplexity Sonar discovery + DB-backed source management — `3057497`
- [x] Successfully published 3 posts to @test908070 (msg IDs 44-46)

### In progress
- [ ] Channel agent v2: review flow with inline buttons + discussion chat editing
- [ ] Source discovery agent: auto-find RSS feeds
- [ ] Admin feedback memory / source quality tracking

### ON HOLD
- [ ] Verify bot admin rights in test chat
- [ ] DDD repository refactor — patch at `docs/ddd-refactor.patch`

### Backlog
- [ ] Multi-agent hierarchy (Coordinator + Moderation/Content/Orchestration/Analytics)
- [ ] Approval workflow: generalized escalation with multi-approver
- [ ] Pyrogram integration
- [ ] Cost control: per-agent budgets, token tracking
- [ ] Analytics agent (scheduled reports)
- [ ] Webapp dashboard for channel management

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

Main Channel (@test908070)
  Published post

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
- 2026-03-05: Client API — separate Pyrogram service account
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
