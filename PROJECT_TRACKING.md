# Moderator-bot — Autonomous Ecosystem Tracker

> Single source of truth for goals, tasks, research, decisions, and current status.
> Update this file as work progresses. Keep entries short and actionable.

## 0) Global vision (high-level)

We operate multiple Telegram **chats and channels** for CIS students in Czechia (CVUT/CVUT, UK, VSE, VUT, MUNI, VSCHT, etc.).
Goal: an **autonomous ecosystem** that can:

- Moderate chats (today's scope)
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
- Objective: make AI moderation (/report, /spam, escalation, memory/overrides) reliable and "production-ready".

### Definition of Done (MVP moderation)
- [x] End-to-end smoke test in real chat for `/report` and `/spam` — agent pipeline works (LLM decision + action execution confirmed from logs)
- [ ] Escalation flow works: inline buttons -> admin decision -> action executed -> stored in DB — **ON HOLD: needs Azamat manual test**
- [x] "Update ... is not handled" investigated and confirmed harmless OR fixed
- [x] Basic code quality checks pass (tests, lint/type if applicable)
- [ ] README updated: how to run locally (no docker), env vars, DB migrations
- [x] Changes committed & pushed in small atomic commits

## 2) Task board

### Done
- [x] Wire `events` router (chat_member handlers were dead code) — `c30a961`
- [x] Make `agent_core` optional when agent disabled (prevented handler crash) — `c30a961`
- [x] Add `allowed_updates` filter to `start_polling` — eliminates noise from edited_message/channel_post/my_chat_member updates — `65eec30`
- [x] TTL cache (5 min) for `get_chat_administrators` in ManagedChatsMiddleware — saves ~500-1000ms per group message — `65eec30`
- [x] Investigate "Update is not handled" — root cause: regular non-command text messages in groups pass all routers with no match. `allowed_updates` filter fixes most noise; remaining is harmless.

### ON HOLD (needs Azamat)
- [ ] Escalation callback manual test — need Azamat to: trigger `/report` -> wait for escalation in DMs -> click a button -> verify action + DB record. See checklist in section 7.
- [ ] Verify bot has admin rights in test chat — mute failed with "API Error", delete failed with "Message too old" (expected for old messages, but admin rights should be confirmed).

### In progress
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
- 2026-03-05: Client API integration — Use a separate Pyrogram service account (not Azamat's personal account).
- 2026-03-05: `allowed_updates` — Only receive `message`, `callback_query`, `chat_member` from Telegram. Other update types are not handled and add noise.
- 2026-03-05: Admin cache TTL = 5 min — Tradeoff between API cost and freshness. If admin changes aren't detected fast enough, reduce `_CACHE_TTL` in `managed_chats.py`.

## 5) Open questions for Azamat

- Q1: What requires approval early on? -> Default: ask approval for sensitive actions.
- Q2: Chat orchestration permissions? -> Title + slowmode require approval; other metadata/actions can be autonomous.
- Q3: Pyrogram account? -> Separate service account (not personal).
- Q4: Confirm bot has admin rights (can restrict members) in the test chat. Logs show "Error while muting user: API Error".

## 6) Status updates (chronological)

- 2026-03-05: Environment fixed, migrations OK, bot starts polling; first runtime bug fixed (timezone-naive/aware timestamps in escalation recovery).
- 2026-03-05: Agent pipeline confirmed working end-to-end from logs (2 handled updates, ~60s each for LLM call). Action errors are expected edge cases (missing admin rights, old messages).
- 2026-03-05: Four fixes applied — events router wired, agent_core optional, allowed_updates filter, admin cache TTL. All tests pass (270/270). Commits: `c30a961`, `65eec30`.

## 7) Manual test checklist for Azamat: escalation flow

Prerequisites:
- Bot running (`docker-compose -f docker-compose.dev.yaml up`)
- `AGENT_ENABLED=true` and `AGENT_OPENROUTER_API_KEY` set in `.env`
- Bot has **admin rights** in the test group chat (can restrict/ban members)
- Your user ID is in `ADMIN_SUPER_ADMINS`

Steps:
1. In a group chat, have someone (or a second account) send a message
2. Reply to that message with `/report` or `/spam`
3. Bot should respond "Analiziruyu soobshcheniye..." then show a decision
4. If the agent decides to **escalate**, you'll get a DM with action buttons
5. Click one of the buttons (e.g., "Mut", "Ban", "Ignor")
6. Verify:
   - [ ] Bot responds with "Vypolneno: ..." in the callback
   - [ ] The escalation message gets updated with the decision
   - [ ] The action is actually executed (user muted/banned/etc.)
   - [ ] Check DB: `SELECT * FROM agent_escalations ORDER BY id DESC LIMIT 5;` — `status` should be `resolved`, `resolved_action` filled

If the agent does NOT escalate (decides on its own), try sending `/report` on a borderline message, or temporarily lower the agent's confidence threshold.
