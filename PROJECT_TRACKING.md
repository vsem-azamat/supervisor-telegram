# Moderator-bot — Autonomous Ecosystem Tracker

> Single source of truth for goals, tasks, research, decisions, and current status.
> Update this file as work progresses. Keep entries short and actionable.

## 0) Global vision (high-level)

We operate multiple Telegram **chats and channels** for CIS students in Czechia (ČVUT/CVUT, UK, VŠE, VUT, MUNI, VŠCHT, etc.).
Goal: an **autonomous ecosystem** that can:

- Moderate chats (today’s scope)
- Autonomously run channels: find resources/topics, produce posts, schedule, adapt
- Communicate with Azamat: ask for approvals early, escalate important questions
- Orchestrate chats/channels metadata: descriptions, pins, rules, titles, etc.
- Potentially use Telegram Client API (Pyrogram) for advanced actions (ads outreach, richer automation)

Constraints:
- Minimize cost (model/tool usage efficiency matters)
- Architecture can evolve
- No artificial limits on tools (we can integrate what we need)

## 1) Current branch / scope

- Repo: `moderator-bot`
- Branch: `claude/telegram-chat-bot-JfIPd`
- Objective: make AI moderation (/report, /spam, escalation, memory/overrides) reliable and “production-ready”.

### Definition of Done (MVP moderation)
- [ ] End-to-end smoke test in real chat for `/report` and `/spam`
- [ ] Escalation flow works: inline buttons → admin decision → action executed → stored in DB
- [ ] “Update … is not handled” investigated and confirmed harmless OR fixed
- [ ] Basic code quality checks pass (tests, lint/type if applicable)
- [ ] README updated: how to run locally (no docker), env vars, DB migrations
- [ ] Changes committed & pushed in small atomic commits

## 2) Task board

### In progress
- [ ] Smoke-test `/report` and `/spam` end-to-end
- [ ] Verify escalation + admin override behavior
- [ ] Investigate log noise: `Update id=... is not handled`
- [ ] Improve docs/README

### Backlog (next)
- [ ] Channel/content agent (autonomous content generation + scheduling)
- [ ] Hierarchy of subagents (roles + tool access boundaries)
- [ ] Approval/permission workflow design (ask-approve-execute loop)
- [ ] Chat/channel orchestration tools (pin/title/description/rules)
- [ ] Pyrogram integration plan (Client API capabilities, safety)

## 3) Research queue (parallel)

Goal: learn from recent experiments in autonomous multi-agent systems and long-term memory that worked in practice.

### Topics
- [ ] Multi-agent orchestration patterns (manager/worker, planner/executor, debate/reviewer)
- [ ] Cost control tactics (cheap model routing, caching, retrieval, budget caps)
- [ ] Long-term memory approaches (DB-backed, retrieval + reflection, feedback loops)
- [ ] Telegram automation architectures (Bot API + Client API hybrid)

### Findings (append as you go)
- (empty)

## 4) Decisions log (ADR-lite)

Record only decisions that matter later.

- 2026-03-05: Approval policy — Ask for approval by default on sensitive actions; specifically title changes and slowmode changes always require explicit approval. Other orchestration actions can be autonomous.
- 2026-03-05: Client API integration — Use a separate Pyrogram service account (not Azamat’s personal account).

## 5) Open questions for Azamat

- Q1: What requires approval early on? → Default: ask approval for sensitive actions.
- Q2: Chat orchestration permissions? → Title + slowmode require approval; other metadata/actions can be autonomous.
- Q3: Pyrogram account? → Separate service account (not personal).

## 6) Status updates (chronological)

- 2026-03-05: Environment fixed, migrations OK, bot starts polling; first runtime bug fixed (timezone-naive/aware timestamps in escalation recovery).
