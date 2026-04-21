# Konnekt Admin Web UI — Design Spec

**Date:** 2026-04-21
**Status:** Draft
**Branch:** `feat/web-ui-scaffold` (scaffold merged; phase plans open subsequent branches)

## Goal & Non-goals

**Goal.** Build a web-based operational command center for managing the
Konnekt Telegram ecosystem — initially observational (dashboards over
channels, chats, costs), then progressively mutational (review
approvals, channel CRUD, moderation actions, agent chat).

**Non-goals for this spec.**

- Production deployment (Docker image, reverse proxy, HTTPS, hardened
  auth) — covered by a separate spec when Phase 4 is approaching.
- Mobile-native responsive design. Desktop-first; mobile is graceful
  degradation only.
- Replacing the existing Telegram bots. The web UI augments them; the
  TG UX keeps working throughout every phase.
- Multi-tenant support. Single-admin tool (super_admins set).
- Real-time collaborative editing (OT/CRDT). Not needed for a 1–2
  person admin panel.

## Motivation

The admin experience today is fragmented across three Telegram bots
and a growing mass of channels + managed chats. Specific pain points
raised by the user:

1. **Review queue is manageable but not convenient.** Approving posts
   one-by-one via inline buttons in a TG chat is tolerable; scanning a
   long draft queue is not.
2. **No sense of the chat ecosystem.** Many managed chats, no
   consolidated view of which are active, which are stale, where ads
   ping, where real talk happens. "I don't feel them" — direct quote.
3. **Relationships between chats are invisible.** ČVUT → faculty
   chats → department chats form a tree, but TG has no concept of
   that. We want to model and visualize it.
4. **No observability over LLM spend.** Cost data exists in `cost_tracker`
   but nowhere surfaces it.
5. **Post view stats are blind.** We publish, but don't know what
   worked — Telethon can expose view counts.

A web UI centralizes all of this into one workspace, and opens the
door to future dashboards (views analytics, agent chat, graph
visualizations).

## Stack

Already scaffolded in `feat/web-ui-scaffold`:

- **Frontend:** SvelteKit 2 + Svelte 5 + TypeScript, Tailwind v4,
  shadcn-svelte. Vite dev server on `:5173`.
- **Backend:** FastAPI + uvicorn. Reuses `app.db.models` and the
  shared async `session_maker`. Dev server on `:8787`.
- **Dev proxy:** Vite forwards `/api/*` → `:8787` so the browser sees
  one origin.
- **Type safety:** OpenAPI generated from FastAPI + `openapi-typescript`
  produces `webui/src/lib/api/types.ts`. Manual `pnpm run api:sync`
  script when schemas change.
- **Auth:** none yet. Firewall-restricted access on `:5173` during
  Phase 0–3; Telegram Login Widget added in Phase 4.
- **State / data fetching:** SvelteKit `load()` for page data; Svelte 5
  runes (`$state` + `$effect`) for polling tiles. TanStack Query
  intentionally deferred.

## Home dashboard — selected tiles

From a 12-option brainstorm, user selected 8 tiles for the home above-
the-fold:

**Channels (content pipeline):**

1. Drafts queue (count by channel, drill → `/posts?status=draft`) `[DB]`
2. Scheduled posts (next 24h mini-calendar, drill → `/posts?scheduled`) `[DB]`
3. LLM cost (week) — breakdown by model / role `[DB]`
4. Post views — median, top/bottom 5 last 7 days `[TG]`

**Chats (moderation):**

5. Chat activity heatmap — chat × hour grid `[TG]`
6. Members delta — +/− per chat over 24h / 7d `[TG]`
7. Spam/ad pings — external channel/@username mentions `[NEW]`
8. Chat relationship graph — mini tree preview, full view at `/chats/graph` `[NEW]`

Tags: `[DB]` = uses existing SQLAlchemy models, no external I/O.
`[TG]` = requires Telethon aggregation (cached). `[NEW]` = needs new
model or detector.

Home ships **day 1 with all 8 tiles present**. `[DB]` tiles show real
data; `[TG]` and `[NEW]` tiles show skeleton + "coming in phase N"
footer until their phase lands. No clicking into nothing — each
skeleton tile is non-interactive.

## Information architecture

```
/                    Home (8 tiles)
├── /posts           List with filters (status, channel, date)
├── /posts/:id       Post detail — preview, images, history
├── /channels        Channels list
├── /channels/:id    Channel detail — RSS sources, schedule, footer
├── /chats           Chats overview — heatmap, members, spam feed
├── /chats/:id       Chat detail — history, moderation, settings
├── /chats/graph     Full tree viewer (parent/child chats)
├── /costs           LLM spend breakdown
├── /agent           Chat with the assistant agent (SSE streaming)
└── /settings        Global settings, super_admins, footers
```

All routes exist from Phase 0 as skeletons. Content fills in per
phase (see below).

## Phasing

Each phase delivers value on its own. Mutation features are
intentionally last — everything through Phase 3 is read-only with
stubbed action buttons.

### Phase 0 — Foundation *(~1 session)*

- App shell: header, left-nav, content area. Desktop-first.
- All routes registered as skeletons ("coming in phase N").
- shadcn components installed: `button`, `card`, `badge`, `table`,
  `skeleton`, `sheet`, `input`, `sonner` (toasts).
- Middleware `require_super_admin` in FastAPI — passes everything in
  dev, wired for future enforcement.
- OpenAPI → TS type-gen script wired.

### Phase 1 — Home + DB pages *(~2–3 sessions)*

Everything readable from our own database.

- **`/`** — home with all 8 tiles; the 3 `[DB]` tiles live, the
  remaining 5 skeleton.
- **`/posts`** — filterable table (status, channel, date). Destination
  for the Drafts and Scheduled tiles.
- **`/posts/:id`** — preview + images + source history. Action buttons
  (approve/reject/edit) are **stubs** that toast "Use TG for now".
- **`/channels`** + **`/channels/:id`** — view-only. RSS sources,
  schedule, footer, recent run stats.
- **`/costs`** — daily/weekly breakdown from `cost_tracker`, grouped
  by model, role, channel.

### Phase 2 — Chats + Telethon *(~2 sessions)*

The half of the project the user "doesn't feel" yet.

- Backend: `app/webapi/services/telethon_stats.py` — thin cached
  aggregator over `TelethonClient`. TTLCache per-method, 60–300s
  depending on cost.
- **`/chats`** + **`/chats/:id`** — chat list, activity heatmap,
  member delta history.
- Home tiles wired to live data: Post views, Chat heatmap,
  Members delta.

### Phase 3 — "Hard" features *(~3–4 sessions)*

- **`/agent`** — web chat with assistant agent. SSE streaming over
  existing `create_assistant_agent()`. Messages, tool traces, token
  stream. History persisted per-user in DB via a new
  `agent_conversations` table (exact row shape decided in the
  Phase 3 plan).
- **Spam / ad detector** — v1 heuristic (regex for t.me links,
  `@username` mentions of non-whitelisted channels). Home tile + feed
  on `/chats/:id`.
- **`/chats/graph`** — adds `parent_chat_id: int | None` to `Chat`
  model (one migration, no M:N table). Nested list + collapse/expand
  viewer. Canvas/force-directed graph deferred unless needed.

### Phase 4 — Mutations + auth *(~1–2 sessions)*

- Approve/reject/edit post via UI — reuses existing review service.
- Channel settings edit — RSS add/remove, schedule, footer.
- Chat moderation actions — ban/unban, blacklist add.
- `/settings` functional.
- **Auth goes live** — Telegram Login Widget → session cookie → server
  verifies `user_id ∈ super_admins`. New `admin_sessions` table, 30-day
  TTL.

## Tech layer

### Data sources and caching

| Source | Latency | Caching |
|---|---|---|
| DB (SQLAlchemy) | <50ms | none |
| Telethon (Client API) | 200–2000ms | in-memory TTLCache, 60–300s per method |
| Derived (spam detector, cost aggregations) | varies | async-compute, persist to DB |

Telethon calls flow through `app/webapi/services/telethon_stats.py`.
Cache key = `(method, tuple(args))`. TTL tuned per-endpoint:

- `get_chat_member_count`: 300s
- `get_recent_activity` (for heatmap): 120s
- `get_post_views`: 600s

This protects the Telethon account against flood-wait when multiple
tiles or tabs refresh simultaneously.

### Update cadence

- **Polling, not WebSocket.** Each live tile has a Svelte `$effect`
  with `setInterval(30_000)`, plus a manual refresh button that
  invokes the same fetch.
- **Exception:** `/agent` uses SSE for token-by-token agent output.
  SSE is sufficient (one-way server → client); WebSocket would add
  reconnect/heartbeat complexity for no gain.
- **No sub-second latency requirement.** 30–60s is acceptable for all
  admin dashboards.

### Backend structure

```
app/webapi/
├── main.py                     # app factory, CORS, router mounting
├── deps.py                     # get_session, get_telethon, require_super_admin
├── schemas/                    # Pydantic response models, 1 file per resource
│   ├── posts.py
│   ├── channels.py
│   ├── chats.py
│   ├── costs.py
│   └── stats.py
├── routes/
│   ├── health.py
│   ├── posts.py
│   ├── channels.py
│   ├── chats.py
│   ├── costs.py
│   ├── agent.py                # SSE stream
│   └── stats.py                # home aggregator tiles
└── services/
    ├── telethon_stats.py       # cached Telethon wrapper
    └── spam_detector.py        # Phase 3
```

API prefixes: `/api/posts`, `/api/channels`, etc. Swagger at
`/api/docs`.

### Frontend data flow

- **Page-level:** SvelteKit `+page.ts` `load()` for initial data.
- **Tile-level:** `useLivePoll<T>(url, intervalMs)` hook — a thin
  wrapper over `$state` + `$effect` + `setInterval`. One
  implementation, used by every polling tile.
- **API client:** `$lib/api/client.ts` — typed `fetch` wrapper using
  generated types, returns `Result<T, ApiError>`.
- **No TanStack Query in Phase 0–2.** Runes cover the scope. If
  invalidation gets messy in Phase 3 (e.g. agent chat + home refresh
  conflicts), revisit.

### Error handling

- **Backend:** FastAPI exception handler returns
  `{"error": {"code": "...", "message": "..."}}` for all non-2xx. HTTP
  status preserved.
- **Frontend:** `apiFetch` centralizes error handling. 4xx/5xx → toast
  via shadcn `sonner`. Result type forces call sites to handle the
  error path.
- **First-load state:** skeleton.
- **Retry state:** inline "Failed to load — [retry]" banner.

### Type safety

```bash
pnpm run api:sync   # webui/package.json script
# runs: openapi-typescript http://127.0.0.1:8787/api/openapi.json \
#       -o src/lib/api/types.ts
```

Run manually on schema change. FE imports from `$lib/api/types` only.

## Thorny pieces

### Auth

- Until Phase 4: no auth code executes. Firewall-gated access by IP to
  `:5173`. `X-Webui-User` header read from `.env` for dev as a stand-in
  identity; middleware is wired from day 1 but is a no-op gate.
- Phase 4: Telegram Login Widget (verified via bot token HMAC) →
  opaque session cookie → server check `user_id ∈ super_admins`. New
  `admin_sessions` table (session_id, user_id, created_at, expires_at).
  30-day TTL. No JWT, no OAuth.

### Agent chat (`/agent`)

AG-UI protocol and OpenAI Agents SDK are **tracked, not adopted
blindly.** Our assistant is PydanticAI; a framework swap for one
feature is not justified.

Approach:

1. `POST /api/agent/turn` SSE endpoint. Accepts user message, streams
   JSON events: `{type: "token" | "tool_call" | "tool_result" | "done"}`.
   Backend reuses `create_assistant_agent()` + `run_stream()` exactly
   as `app/assistant/bot.py` does, just different transport.
2. FE chat UI: shadcn-based message list + textarea. Tool traces
   rendered via the shared `app/core/tool_trace.format_tool_trace` —
   we expose its output in the SSE payload.
3. Conversation persistence: new table `agent_conversations` keyed by
   admin user_id. TTL/eviction policy mirrors the in-memory one from
   the TG assistant (4h idle, LRU cap). Exact row shape (single JSON
   blob of messages vs per-turn rows) is decided in the Phase 3 plan.
4. AG-UI: if our event schema maps cleanly to their protocol, add a
   thin adapter endpoint. If not, ship our own shape — it's internal.

OpenAI Agents SDK: **not adopted.** No concrete capability it
offers that PydanticAI doesn't.

### Chat graph

Start with **tree, not graph.** The ČVUT → faculty → department
structure is hierarchical; M:N graph is YAGNI until a non-hierarchical
use case surfaces (e.g. "this chat advertises that chat" —
not a parent relationship).

Phase 3 data model change:

```python
# app/db/models.py  (Chat class)
parent_chat_id: Mapped[int | None] = mapped_column(
    BigInteger, ForeignKey("chats.id"), nullable=True
)
relation_notes: Mapped[str | None] = mapped_column(String, nullable=True)
```

One field, one migration. `/chats/graph` = collapsible nested list.
No cytoscape.js / d3-force in Phase 3. If a true graph need emerges
(Phase 4+), add `chat_relations(source_id, target_id, kind)` table
alongside the tree column.

### Testing

- **Backend:** `tests/webapi/` with `httpx.AsyncClient` against the
  FastAPI app factory. Reuses existing `db_session_maker` fixtures.
  Telethon calls mocked.
- **Frontend:** Playwright e2e against the running dev stack — 2–3
  scenarios per phase, not exhaustive. Component tests deferred until
  the UI stops churning (Phase 2+).
- **Svelte check** + ruff + ty added to the pre-commit hook starting
  Phase 1.

### Deployment

Out of scope. Dev-mode only through all four phases of this spec.
Production containerization, reverse proxy, HTTPS, rate limiting,
backup strategy — a separate spec opens near the end of Phase 4.

## Open questions (to resolve in phase plans, not this spec)

- Exact `agent_conversations` persistence shape (simple blob of
  messages vs per-turn rows) — decide in Phase 3 plan.
- Graph viewer library choice if tree view proves insufficient — defer
  until post-Phase 3 retrospective.
- Whether to introduce TanStack Query or remain on raw runes — revisit
  mid-Phase 3 if invalidation gets tangled.
- Spam detector precision/recall targets — define with real data
  during Phase 3.

## Exit criteria per phase

Each phase completes when:

- All its routes load with real or explicitly-stubbed content.
- Backend endpoints return typed JSON with generated TS matching.
- The phase's pytest + Playwright scenarios pass.
- `ruff check` + `ty check` + `svelte-check` are clean.
- A short demo video or screenshots attached to the merge PR.

Phase plans (one per phase, written via the writing-plans skill) will
list per-task details, file paths, test expectations.

## Appendix — user decisions captured during brainstorm

1. Command-center orientation (operational observability first,
   mutations later) — chosen over review-first / CRUD-first.
2. Unified home dashboard covering both channels and chats, with
   drill-down — chosen over separate apps.
3. Full 8-tile home day 1 with skeletons for unready tiles — chosen
   over phased tile rollout.
4. All 7 candidate sections (`/posts`, `/channels`, `/chats`,
   `/chats/graph`, `/costs`, `/agent`, `/settings`) in scope — user
   delegated ordering to the architect; ordering is the four-phase
   plan above.
5. Polling over WebSocket. TanStack Query deferred. Tree over graph
   for chat relationships.
