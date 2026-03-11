# Architecture Plan: Autonomous Telegram Ecosystem

> Consolidated output from 7 parallel design/research agents, 2026-03-06.
> This document captures all architecture decisions, designs, and research findings.

## Table of Contents

1. [Multi-Agent Hierarchy](#1-multi-agent-hierarchy)
2. [Channel/Content Agent](#2-channelcontent-agent)
3. [Approval Workflow](#3-approval-workflow)
4. [Pyrogram Integration](#4-pyrogram-integration)
5. [Cost Control & Memory](#5-cost-control--memory)
6. [DDD Repository Refactor](#6-ddd-repository-refactor)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Multi-Agent Hierarchy

### Architecture

```
                    +---------------------+
                    |     Coordinator      |
                    |  (deterministic Python,
                    |   NOT an LLM agent)  |
                    +----------+----------+
                               |
            +----------+-------+-------+----------+
            |          |               |          |
    +-------v------+ +v------------+ +v--------+ +v----------+
    |  Moderation  | |   Content   | | Orchestr| | Analytics |
    |    Agent     | |    Agent    | |  Agent  | |   Agent   |
    |  (exists)    | |  (planned)  | |(planned)| | (planned) |
    +--------------+ +-------------+ +---------+ +-----------+
```

### Key Decisions

- **Coordinator is deterministic code** -- no LLM tokens for routing. At 4 agents with well-defined triggers, routing is a `match` statement, not an AI decision.
- **Per-agent PydanticAI instances** -- strict tool isolation, independent models, independent budgets.
- **DB-backed task queue** (`agent_tasks` table) -- no Redis/RabbitMQ. PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` is sufficient at this scale.
- **TelegramActionGuard** -- Bot proxy enforcing per-agent API permissions.
- **Agent-as-tool pattern** (PydanticAI native) for cross-agent delegation when needed.

### Agent Roles

| Agent | Trigger | Model | Actions | Approval |
|-------|---------|-------|---------|----------|
| Moderation | /report, /spam | gemini-2.0-flash | mute, ban, delete, warn, blacklist, escalate | On escalate only |
| Content | Scheduled, /content | gemini-2.5-flash or claude-haiku | Draft, publish, schedule | Always for publish |
| Orchestration | /orchestrate, scheduled | gemini-2.0-flash | Titles, descriptions, pins, rules | Title+slowmode only |
| Analytics | Scheduled, /analytics | gemini-2.0-flash | Read-only queries, reports | Never |

### New DB Tables

- `agent_tasks` -- inter-agent task queue (source_agent, target_agent, status, payload, scheduled_for)
- `agent_cost_log` -- per-agent LLM cost tracking (agent_name, model, tokens, cost_usd)
- `agent_registry` -- runtime agent config (name, enabled, model, budget, config_json)

### File Structure

```
app/agent/
  base.py              # BaseAgent ABC
  registry.py          # AgentRegistry (Python class)
  coordinator.py       # Coordinator: dispatch, priority, scheduling
  guard.py             # TelegramActionGuard (Bot API permission proxy)
  cost.py              # CostTracker
  task_queue.py         # TaskQueue (DB-backed)
  agents/
    moderation.py      # Refactored from current core.py
    content.py
    orchestration.py
    analytics.py
  tools/
    telegram.py        # Telegram API wrappers
    search.py          # Web search (content agent)
    db_queries.py      # Common DB query helpers
```

---

## 2. Channel/Content Agent

### Pipeline

```
[1] DISCOVER  -->  [2] SCREEN  -->  [3] GENERATE  -->  [4] REVIEW  -->  [5] PUBLISH
    (fetch)       (cheap LLM)     (quality LLM)     (auto/admin)     (Telegram API)
```

### Cost Model

- Screening: gemini-2.0-flash at ~$0.00001/call
- Generation: claude-sonnet at ~$0.003/call
- Daily cost for 100 items scanned + 3 posts generated: ~$0.05

### New Domain Entities

- `ChannelConfigEntity` -- per-channel settings (topics, language, tone, frequency, sources, require_approval)
- `ContentSourceEntity` -- RSS, Telegram channel, or web page source
- `ContentItemEntity` -- raw discovered content with relevance score
- `PostDraftEntity` -- generated post with status lifecycle (draft -> pending_approval -> scheduled -> published)
- `PostPerformanceEntity` -- engagement tracking (views, reactions, forwards)

### Config

```python
class ChannelAgentSettings(BaseSettings):
    enabled: bool = False
    screening_model: str = "google/gemini-2.0-flash-001"
    generation_model: str = "anthropic/claude-sonnet-4-20250514"
    fetch_interval_minutes: int = 60
    relevance_threshold: float = 0.6
    default_require_approval: bool = True
    max_daily_cost_usd: float = 1.0
```

### New Dependency

- `feedparser` for RSS parsing

---

## 3. Approval Workflow

### Generalizing Escalation

The current `EscalationService` (moderation-only) evolves into a general `ApprovalService` supporting any action type.

### New DB Tables

**`approval_requests`** (replaces `agent_escalations` over time):
- request_type, priority, status
- requester_type/id, chat_id, target_user_id
- context_data (JSON), proposed_action, action_params (JSON)
- required_approvers, approver_role
- admin_messages (JSON: {admin_id: message_id})
- timeout_policy, timeout_at
- resolved_action, resolved_at

**`approval_votes`** (for multi-approver):
- request_id (FK), admin_id, vote, chosen_action, comment, voted_at

### State Machine

```
PENDING --> APPROVED (quorum reached)
PENDING --> REJECTED (any reject for single-approver)
PENDING --> TIMEOUT --> auto_approve / auto_reject / re_escalate
PENDING --> CANCELLED
```

### Action Executor Registry

```python
register_action("moderation", execute_moderation_action)
register_action("channel_post", execute_channel_post)
register_action("chat_title_change", execute_title_change)
```

### Migration Path

1. Add new tables alongside existing `agent_escalations`
2. Rewire `AgentCore._do_escalate()` to use `ApprovalService`
3. Support both `esc:` and `apr:` callback prefixes during transition
4. Remove old `EscalationService` once all pending resolved

---

## 4. Pyrogram Integration

### Architecture: Same process, shared event loop

Pyrogram is async, runs alongside aiogram naturally. No IPC needed.

### Key Capabilities (Bot API cannot do)

- Read full message history
- Search messages across chats
- User profile scraping (bio, photos, last seen)
- Join/leave channels programmatically
- Channel statistics
- Scheduled messages
- Full member list enumeration

### Module Structure

```
app/infrastructure/telegram_client/
  client.py          # PyrogramClient wrapper
  rate_limiter.py    # Token bucket + human-like delays
  services/
    history.py       # Message history reading
    search.py        # Message search
    profiles.py      # User profiles
    channels.py      # Channel management
```

### Safety

| Risk Level | Actions | Rate |
|-----------|---------|------|
| Low | Read messages, get profiles | 20-30/min |
| Medium | Send to known groups | 5-10/min |
| High | Join new groups, outreach | 1-3/min |

- Circuit breaker: 3+ FloodWaits in 10min -> pause 30min
- File-based sessions in persistent Docker volume
- Dedicated service account (not personal)
- Account warm-up: 1-2 weeks manual usage before automation

### Phases

1. Foundation (client wrapper, rate limiter, config, auth script)
2. Read-only services (history, search, profiles)
3. Channel management (stats, scheduling)
4. Outreach (future, highest risk)

---

## 5. Cost Control & Memory

### Cost Control

- **Model routing**: gemini-flash for 90% of tasks, stronger models only for content generation
- **Token tracking**: Add `tokens_used`, `cost_usd` columns to `AgentDecision`; parse OpenRouter `x-openrouter-cost` header
- **Budget caps**: Per-agent daily budgets, checked before dispatch; fallback to escalate-to-admin if exceeded
- **Prompt caching**: Cache corrections injection for 5 min (currently queries DB every call)

### Cost Benchmarks

| Model | Cost per decision | 1000/day |
|-------|------------------|----------|
| Gemini Flash | $0.00001-0.00005 | $0.01-0.05 |
| GPT-4o-mini | $0.0001-0.0003 | $0.10-0.30 |
| Claude Haiku | $0.0001-0.0002 | $0.10-0.20 |
| Claude Sonnet | $0.001-0.005 | $1.00-5.00 |

### Memory Evolution

1. **Current**: `AgentDecision` log + `UserRiskProfile` queries + correction injection (solid foundation)
2. **Add**: `agent_behavior_rules` table -- extracted from correction patterns, included in system prompt
3. **Add**: Nightly reflection task -- analyze corrections, generate rules
4. **Plan**: Pruning at 50k+ rows -- summarize old decisions, archive raw data
5. **Avoid**: Vector DB (overkill at this scale), unbounded context injection

### Recommended Pattern

PydanticAI agent-as-tool for cross-agent delegation. No message bus until 5+ agents.

---

## 6. DDD Repository Refactor

### Status: Code complete in worktree, needs clean merge

The agent layer (`memory.py`, `escalation.py`) has been refactored to use repository interfaces:

### New Entities (in `app/domain/entities.py`)

- `AgentDecisionEntity` -- dataclass with user_id, chat_id, event_type, action, reason, confidence, etc.
- `AgentEscalationEntity` -- dataclass with chat_id, target_user_id, status, suggested_action, resolve/timeout methods

### New Interfaces (in `app/domain/repositories.py`)

- `IAgentDecisionRepository` -- log_decision, get_user_risk_profile, get_recent_decisions, get_chat_decisions, get_admin_corrections
- `IAgentEscalationRepository` -- create, get_by_id, get_pending_by_chat, resolve, recover_pending, update

### New Implementations

- `app/infrastructure/db/repositories/agent_decision.py`
- `app/infrastructure/db/repositories/agent_escalation.py`

### Changes to Agent Layer

- `AgentMemory.__init__` takes `IAgentDecisionRepository` instead of `AsyncSession`
- `EscalationService` takes `IAgentEscalationRepository` instead of `AsyncSession`
- `AgentDeps` includes repositories instead of raw session
- `DependenciesMiddleware` injects repository instances

---

## 7. Implementation Roadmap

### Phase 1: Foundation (Week 1)
1. DDD repository refactor for agent models (merge from worktree)
2. BaseAgent ABC + AgentRegistry + Coordinator
3. Agent cost tracking (agent_cost_log table)
4. TelegramActionGuard
5. Refactor AgentCore -> ModerationAgent(BaseAgent)

### Phase 2: Approval System (Week 2)
6. ApprovalRequest + ApprovalVote tables + migration
7. ApprovalService (generalized from EscalationService)
8. Action executor registry
9. Wire moderation escalation through new approval system
10. /pending command for batch approvals

### Phase 3: Analytics Agent (Week 2-3)
11. AnalyticsAgent with read-only tools
12. Scheduled daily/weekly reports
13. /analytics command handler

### Phase 4: Content Agent (Week 3-4)
14. Channel config DB models + admin commands
15. ContentFetcher (RSS first)
16. ScreeningAgent (cheap LLM relevance scoring)
17. GenerationAgent (quality LLM post creation)
18. Publisher with scheduling
19. Content approval flow

### Phase 5: Orchestration + Pyrogram (Week 5-6)
20. OrchestrationAgent for chat metadata
21. Pyrogram foundation (client, rate limiter, auth)
22. Read-only Pyrogram services (history, search, profiles)
23. Agent tools using Pyrogram data

### Phase 6: Hardening (Ongoing)
24. Budget alerts and cost dashboards
25. Memory reflection (nightly rule extraction)
26. Webapp integration (approval dashboard, analytics)
27. Cross-agent learning
28. Memory pruning at scale

---

## Anti-Patterns to Avoid

1. **No message bus until 5+ agents** -- DB task queue is sufficient
2. **No vector DB at this scale** -- PostgreSQL full-text search is enough
3. **No LLM coordinator** -- deterministic routing saves tokens
4. **No unbounded context injection** -- limit to 5 items per category
5. **No semantic caching** -- infrastructure cost exceeds savings at this volume
6. **No personal Telegram account for automation** -- dedicated service account only
7. **No tight coupling to Telegram** -- abstract actions behind interfaces
