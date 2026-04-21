# Web UI Phase 0 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the scaffold from `feat/web-ui-scaffold` into a navigable empty shell — every route in the IA exists with a "coming in phase N" placeholder, the sidebar/header chrome is in place, shadcn building blocks are installed, a `require_super_admin` dependency is wired (no-op in dev), and OpenAPI→TS type generation is one-command away.

**Architecture:** Two processes (FastAPI on `:8787`, SvelteKit on `:5173`) with Vite proxying `/api/*` — already running from the scaffold. Phase 0 adds an app-shell layout (`Sidebar` + `Header` + slot) around every route, a single `ComingSoon` component used by every non-Phase-0 route, and a thin typed API client. No real data fetching beyond what the scaffold already does — that's Phase 1.

**Tech Stack:** SvelteKit 2, Svelte 5 (runes), TypeScript, Tailwind v4, shadcn-svelte, FastAPI, Pydantic, pytest, `openapi-typescript`.

**Branch:** `feat/web-ui-phase-0-foundation` — branch from the tip of `feat/web-ui-scaffold` (scaffold is still unmerged; rebase on `main` after scaffold lands).

**Design doc:** `docs/superpowers/specs/2026-04-21-web-ui-scope-design.md`

---

## File structure at end of Phase 0

```
app/webapi/
├── __init__.py                      (unchanged)
├── __main__.py                      (unchanged)
├── deps.py                          + require_super_admin dep
├── main.py                          (unchanged)
├── schemas.py                       (unchanged)
└── routes/
    ├── __init__.py                  (unchanged)
    ├── health.py                    (unchanged)
    └── posts.py                     + Depends(require_super_admin)

tests/webapi/
├── __init__.py                      NEW
├── conftest.py                      NEW — settings-override fixture
└── test_deps.py                     NEW — require_super_admin tests

webui/
├── package.json                     + api:sync script, openapi-typescript dep
├── src/
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts            NEW
│   │   │   └── types.ts             NEW (generated)
│   │   └── components/
│   │       ├── app-shell/
│   │       │   ├── Header.svelte    NEW
│   │       │   └── Sidebar.svelte   NEW
│   │       ├── ComingSoon.svelte    NEW
│   │       └── ui/                  shadcn-installed
│   │           ├── badge/
│   │           ├── button/
│   │           ├── card/
│   │           ├── input/
│   │           ├── sheet/
│   │           ├── skeleton/
│   │           ├── sonner/
│   │           └── table/
│   └── routes/
│       ├── +layout.svelte           ← app shell wraps {children}
│       ├── +page.svelte             ← home skeleton
│       ├── posts/+page.svelte       NEW skeleton
│       ├── posts/[id]/+page.svelte  NEW skeleton
│       ├── channels/+page.svelte    NEW skeleton
│       ├── channels/[id]/+page.svelte NEW skeleton
│       ├── chats/+page.svelte       NEW skeleton
│       ├── chats/[id]/+page.svelte  NEW skeleton
│       ├── chats/graph/+page.svelte NEW skeleton
│       ├── costs/+page.svelte       NEW skeleton
│       ├── agent/+page.svelte       NEW skeleton
│       └── settings/+page.svelte    NEW skeleton
```

---

## Preflight

- [ ] **Confirm dev stack runs**

Run (two terminals):

```bash
uv run -m app.webapi
pnpm --dir webui run dev
```

Expected: `curl -s http://localhost:5173/api/health` returns `{"status":"ok"}`. If not, fix before proceeding.

- [ ] **Create the branch**

```bash
git checkout -b feat/web-ui-phase-0-foundation
```

---

## Task 1: `require_super_admin` FastAPI dependency (no-op in dev)

**Files:**
- Create: `tests/webapi/__init__.py`
- Create: `tests/webapi/conftest.py`
- Create: `tests/webapi/test_deps.py`
- Modify: `app/webapi/deps.py`

Rationale: Phase 4 replaces the body with real session-cookie verification. Phase 0 wires it in so endpoints already declare their auth requirement — turning it on later is one-line.

- [ ] **Step 1.1: Create the test package**

Create `tests/webapi/__init__.py` (empty file):

```python
```

- [ ] **Step 1.2: Create the test fixture**

Create `tests/webapi/conftest.py`:

```python
"""Shared fixtures for webapi tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from app.core.config import settings


@pytest.fixture()
def override_super_admins() -> Iterator[None]:
    """Context manager style: set settings.admin.super_admins for the test
    and restore afterwards. Used by tests that exercise the auth dep."""
    original = list(settings.admin.super_admins)
    yield
    settings.admin.super_admins = original
```

- [ ] **Step 1.3: Write the failing test**

Create `tests/webapi/test_deps.py`:

```python
"""Tests for webapi dependencies."""

from __future__ import annotations

import pytest
from app.core.config import settings
from app.webapi.deps import require_super_admin
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


async def test_require_super_admin_returns_first_configured(override_super_admins) -> None:
    """In dev the dep returns the first configured super_admin — enough
    for downstream code to treat the request as authenticated."""
    settings.admin.super_admins = [12345, 67890]

    result = await require_super_admin()

    assert result == 12345


async def test_require_super_admin_raises_when_none_configured(override_super_admins) -> None:
    """With zero super_admins there is no identity to attach — the dep
    rejects the request so endpoints never run without an admin context."""
    settings.admin.super_admins = []

    with pytest.raises(HTTPException) as exc_info:
        await require_super_admin()

    assert exc_info.value.status_code == 503
    assert "super_admin" in exc_info.value.detail.lower()
```

- [ ] **Step 1.4: Run tests — verify they fail**

Run:

```bash
uv run -m pytest tests/webapi/test_deps.py -v
```

Expected: FAIL (`ImportError` — `require_super_admin` doesn't exist yet).

- [ ] **Step 1.5: Implement `require_super_admin`**

Append to `app/webapi/deps.py`:

```python
from fastapi import HTTPException


async def require_super_admin() -> int:
    """FastAPI dependency that returns the authenticated admin's user_id.

    Phase 0 stub: returns the first configured super_admin. No real session
    validation — access is gated by firewall in dev. Phase 4 replaces the
    body with session-cookie verification (see Phase 4 plan).
    """
    from app.core.config import settings

    if not settings.admin.super_admins:
        raise HTTPException(
            status_code=503,
            detail="No super_admin configured — set ADMIN_SUPER_ADMINS in .env",
        )
    return settings.admin.super_admins[0]
```

- [ ] **Step 1.6: Run tests — verify they pass**

Run:

```bash
uv run -m pytest tests/webapi/test_deps.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 1.7: Commit**

```bash
git add tests/webapi app/webapi/deps.py
git commit -m "feat(webapi): add require_super_admin dep stub for future auth

Phase 4 will replace the body with real session-cookie verification.
For now endpoints declare their auth requirement and the dep returns
the first configured super_admin."
```

---

## Task 2: Wire `require_super_admin` onto `/api/posts`

**Files:**
- Modify: `app/webapi/routes/posts.py:12-30`

Rationale: prove the dep plugs into a real route. The existing `GET /api/posts` is the only endpoint that reads domain data today.

- [ ] **Step 2.1: Add the dependency to `list_posts`**

Edit `app/webapi/routes/posts.py`. Replace the full file contents with:

```python
"""Channel posts — list endpoint for the review panel."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChannelPost
from app.webapi.deps import get_session, require_super_admin
from app.webapi.schemas import PostRead

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[PostRead])
async def list_posts(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
    status: str | None = Query(default=None, description="Filter by PostStatus"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ChannelPost]:
    stmt = select(ChannelPost).order_by(ChannelPost.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(ChannelPost.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

- [ ] **Step 2.2: Smoke-test the endpoint still responds**

Restart uvicorn (Ctrl-C in the terminal, then `uv run -m app.webapi` again). Then:

```bash
curl -s http://localhost:5173/api/posts?limit=1 | head -c 200
```

Expected: a JSON array starts with `[{"id":...}]` (or `[]` if no posts). If `503`, your `.env` has no `ADMIN_SUPER_ADMINS` — set it.

- [ ] **Step 2.3: Commit**

```bash
git add app/webapi/routes/posts.py
git commit -m "feat(webapi): gate /api/posts behind require_super_admin

Dev: no-op (returns first configured super_admin). Wired now so Phase 4
can flip it to real session validation without touching route code."
```

---

## Task 3: Install shadcn-svelte components

**Files:**
- Create: `webui/src/lib/components/ui/{button,card,badge,table,skeleton,sheet,input,sonner}/*`
- Modify: `webui/package.json` (deps added by shadcn CLI)

Rationale: Phase 0 pages use `Card` + `Badge`, Phase 1+ uses the rest. Install them all in one commit so subsequent work doesn't get interrupted.

- [ ] **Step 3.1: Run the shadcn CLI (interactive — needs a real TTY)**

**Important:** the shadcn-svelte CLI prompts for confirmation. Run this from an interactive terminal, not the Claude sandbox. Press Enter at each prompt to accept defaults.

```bash
cd webui
pnpm dlx shadcn-svelte@latest add button card badge table skeleton sheet input sonner --overwrite --skip-preflight
```

Expected: `src/lib/components/ui/` contains 8 subdirectories (`button/`, `card/`, `badge/`, `table/`, `skeleton/`, `sheet/`, `input/`, `sonner/`), each with one or more `.svelte` files.

- [ ] **Step 3.2: Verify type-check still passes**

Run:

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 3.3: Commit**

```bash
git add webui/src/lib/components/ui webui/package.json webui/pnpm-lock.yaml
git commit -m "feat(webui): install shadcn-svelte components (button/card/badge/table/skeleton/sheet/input/sonner)

Building blocks for Phase 0 shell and all later pages."
```

---

## Task 4: OpenAPI → TypeScript type generation

**Files:**
- Modify: `webui/package.json`
- Create: `webui/src/lib/api/types.ts` (generated)

Rationale: every endpoint we add in Phase 1+ ships typed from day one. One script, run manually after schema changes.

- [ ] **Step 4.1: Install the generator**

```bash
pnpm --dir webui add -D openapi-typescript
```

Expected: `package.json` devDependencies gains `"openapi-typescript": "^7.x"`.

- [ ] **Step 4.2: Add the `api:sync` script**

Edit `webui/package.json`. Under `"scripts"`, add:

```json
"api:sync": "openapi-typescript http://127.0.0.1:8787/api/openapi.json -o src/lib/api/types.ts"
```

Resulting `scripts` block looks like:

```json
"scripts": {
  "dev": "vite dev",
  "build": "vite build",
  "preview": "vite preview",
  "prepare": "svelte-kit sync || echo ''",
  "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
  "check:watch": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json --watch",
  "api:sync": "openapi-typescript http://127.0.0.1:8787/api/openapi.json -o src/lib/api/types.ts"
}
```

- [ ] **Step 4.3: Generate types for the first time**

Make sure the FastAPI dev server is running (`uv run -m app.webapi`), then:

```bash
pnpm --dir webui run api:sync
```

Expected: `webui/src/lib/api/types.ts` is created. `head -20 webui/src/lib/api/types.ts` shows an auto-generated header and `export interface paths { "/api/health": ...; "/api/posts": ...; }`.

- [ ] **Step 4.4: Commit**

```bash
git add webui/package.json webui/pnpm-lock.yaml webui/src/lib/api/types.ts
git commit -m "feat(webui): openapi→ts type generation (pnpm run api:sync)

Types land in src/lib/api/types.ts. Manual sync on schema change."
```

---

## Task 5: Thin API client

**Files:**
- Create: `webui/src/lib/api/client.ts`

Rationale: every page fetches through this so error handling and URL building live in one place. Stays under 40 lines through Phase 2.

- [ ] **Step 5.1: Write the client**

Create `webui/src/lib/api/client.ts`:

```typescript
/**
 * Thin typed fetch wrapper. Call sites get back { data } on success or
 * { error } on failure — forces them to handle the failure path.
 *
 * The frontend hits same-origin /api/* which Vite proxies to FastAPI.
 */

export type ApiResult<T> = { data: T; error: null } | { data: null; error: ApiError };

export type ApiError = {
	status: number;
	code: string;
	message: string;
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
	try {
		const res = await fetch(path, {
			...init,
			headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }
		});
		if (!res.ok) {
			const body = await res.json().catch(() => ({}));
			return {
				data: null,
				error: {
					status: res.status,
					code: body?.error?.code ?? `http_${res.status}`,
					message: body?.error?.message ?? body?.detail ?? res.statusText
				}
			};
		}
		const data = (await res.json()) as T;
		return { data, error: null };
	} catch (e) {
		return {
			data: null,
			error: {
				status: 0,
				code: 'network_error',
				message: e instanceof Error ? e.message : String(e)
			}
		};
	}
}
```

- [ ] **Step 5.2: Verify type-check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 5.3: Commit**

```bash
git add webui/src/lib/api/client.ts
git commit -m "feat(webui): typed apiFetch wrapper (Result-style)

Call sites always handle failure. 30 lines, no external deps."
```

---

## Task 6: Sidebar component

**Files:**
- Create: `webui/src/lib/components/app-shell/Sidebar.svelte`

Rationale: fixed left nav with every IA entry. Active route is highlighted via SvelteKit's `page` store.

- [ ] **Step 6.1: Create the Sidebar**

Create `webui/src/lib/components/app-shell/Sidebar.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/state';

	type NavItem = { href: string; label: string; phase?: number };

	const items: NavItem[] = [
		{ href: '/', label: 'Home', phase: 1 },
		{ href: '/posts', label: 'Posts', phase: 1 },
		{ href: '/channels', label: 'Channels', phase: 1 },
		{ href: '/chats', label: 'Chats', phase: 2 },
		{ href: '/chats/graph', label: 'Chat graph', phase: 3 },
		{ href: '/costs', label: 'Costs', phase: 1 },
		{ href: '/agent', label: 'Agent', phase: 3 },
		{ href: '/settings', label: 'Settings', phase: 4 }
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	}
</script>

<nav class="flex h-full w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50">
	<div class="px-4 py-5">
		<span class="text-sm font-semibold tracking-tight text-zinc-900">Konnekt admin</span>
	</div>
	<ul class="flex flex-col gap-0.5 px-2">
		{#each items as item (item.href)}
			<li>
				<a
					href={item.href}
					class="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors
						{isActive(item.href)
						? 'bg-zinc-900 text-white'
						: 'text-zinc-700 hover:bg-zinc-200'}"
				>
					<span>{item.label}</span>
					{#if item.phase}
						<span
							class="rounded-sm px-1.5 py-0.5 text-[10px] font-medium
								{isActive(item.href) ? 'bg-white/20 text-white' : 'bg-zinc-200 text-zinc-600'}"
						>
							P{item.phase}
						</span>
					{/if}
				</a>
			</li>
		{/each}
	</ul>
</nav>
```

- [ ] **Step 6.2: Verify type-check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 6.3: Commit**

```bash
git add webui/src/lib/components/app-shell/Sidebar.svelte
git commit -m "feat(webui): Sidebar with IA nav + phase badges"
```

---

## Task 7: Header component

**Files:**
- Create: `webui/src/lib/components/app-shell/Header.svelte`

Rationale: thin top bar with current page title + placeholder user pill. Leaves room for breadcrumbs/search in later phases.

- [ ] **Step 7.1: Create the Header**

Create `webui/src/lib/components/app-shell/Header.svelte`:

```svelte
<script lang="ts">
	import { page } from '$app/state';

	function currentTitle(pathname: string): string {
		const map: Record<string, string> = {
			'/': 'Home',
			'/posts': 'Posts',
			'/channels': 'Channels',
			'/chats': 'Chats',
			'/chats/graph': 'Chat graph',
			'/costs': 'Costs',
			'/agent': 'Agent',
			'/settings': 'Settings'
		};
		if (map[pathname]) return map[pathname];
		const segments = pathname.split('/').filter(Boolean);
		if (segments[0]) return segments[0].charAt(0).toUpperCase() + segments[0].slice(1);
		return '—';
	}
</script>

<header
	class="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6"
>
	<h1 class="text-base font-medium text-zinc-900">{currentTitle(page.url.pathname)}</h1>
	<div class="flex items-center gap-2 text-xs text-zinc-500">
		<span class="rounded-full bg-zinc-100 px-2.5 py-1 font-medium">dev</span>
		<span>admin</span>
	</div>
</header>
```

- [ ] **Step 7.2: Verify type-check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 7.3: Commit**

```bash
git add webui/src/lib/components/app-shell/Header.svelte
git commit -m "feat(webui): Header with page title + dev badge"
```

---

## Task 8: Wire app shell into the root layout

**Files:**
- Modify: `webui/src/routes/+layout.svelte`

Rationale: every page gets the shell for free. `{@render children()}` renders into the content area.

- [ ] **Step 8.1: Replace `+layout.svelte`**

Replace the contents of `webui/src/routes/+layout.svelte` with:

```svelte
<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import Header from '$lib/components/app-shell/Header.svelte';
	import Sidebar from '$lib/components/app-shell/Sidebar.svelte';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<div class="flex h-screen w-screen bg-white text-zinc-900">
	<Sidebar />
	<div class="flex min-w-0 flex-1 flex-col">
		<Header />
		<main class="flex-1 overflow-auto">
			{@render children()}
		</main>
	</div>
</div>
```

- [ ] **Step 8.2: Visually verify in browser**

With dev servers running, open `http://46.225.117.31:5173/` (or your VPS host) and confirm:

- Left sidebar with 8 items is visible
- Header shows "Home" (no 404)
- Existing posts list from the scaffold still renders inside the main area

- [ ] **Step 8.3: Commit**

```bash
git add webui/src/routes/+layout.svelte
git commit -m "feat(webui): root layout renders app shell around every route"
```

---

## Task 9: `ComingSoon` placeholder component

**Files:**
- Create: `webui/src/lib/components/ComingSoon.svelte`

Rationale: every non-Phase-0 route renders this. One file to update when we want the message to change.

- [ ] **Step 9.1: Create the component**

Create `webui/src/lib/components/ComingSoon.svelte`:

```svelte
<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';

	type Props = { title: string; phase: number; note?: string };

	let { title, phase, note }: Props = $props();
</script>

<div class="mx-auto max-w-2xl px-6 py-10">
	<Card.Root>
		<Card.Header class="flex flex-row items-center justify-between">
			<Card.Title>{title}</Card.Title>
			<Badge variant="secondary">Phase {phase}</Badge>
		</Card.Header>
		<Card.Content>
			<p class="text-sm text-zinc-600">
				{note ?? 'This page is part of Phase ' + phase + ' of the rollout. Until then you can still do this in Telegram.'}
			</p>
		</Card.Content>
	</Card.Root>
</div>
```

- [ ] **Step 9.2: Verify type-check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 9.3: Commit**

```bash
git add webui/src/lib/components/ComingSoon.svelte
git commit -m "feat(webui): ComingSoon placeholder component"
```

---

## Task 10: All skeleton route files

**Files:**
- Create: `webui/src/routes/posts/+page.svelte`
- Create: `webui/src/routes/posts/[id]/+page.svelte`
- Create: `webui/src/routes/channels/+page.svelte`
- Create: `webui/src/routes/channels/[id]/+page.svelte`
- Create: `webui/src/routes/chats/+page.svelte`
- Create: `webui/src/routes/chats/[id]/+page.svelte`
- Create: `webui/src/routes/chats/graph/+page.svelte`
- Create: `webui/src/routes/costs/+page.svelte`
- Create: `webui/src/routes/agent/+page.svelte`
- Create: `webui/src/routes/settings/+page.svelte`

Rationale: all routes exist from Phase 0 so the sidebar never 404s. Each file is four lines.

- [ ] **Step 10.1: `/posts`**

Create `webui/src/routes/posts/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Posts" phase={1} />
```

- [ ] **Step 10.2: `/posts/:id`**

Create `webui/src/routes/posts/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Post detail" phase={1} />
```

- [ ] **Step 10.3: `/channels`**

Create `webui/src/routes/channels/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Channels" phase={1} />
```

- [ ] **Step 10.4: `/channels/:id`**

Create `webui/src/routes/channels/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Channel detail" phase={1} />
```

- [ ] **Step 10.5: `/chats`**

Create `webui/src/routes/chats/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Chats" phase={2} />
```

- [ ] **Step 10.6: `/chats/:id`**

Create `webui/src/routes/chats/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Chat detail" phase={2} />
```

- [ ] **Step 10.7: `/chats/graph`**

Create `webui/src/routes/chats/graph/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Chat graph" phase={3} />
```

- [ ] **Step 10.8: `/costs`**

Create `webui/src/routes/costs/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Costs" phase={1} />
```

- [ ] **Step 10.9: `/agent`**

Create `webui/src/routes/agent/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Agent chat" phase={3} />
```

- [ ] **Step 10.10: `/settings`**

Create `webui/src/routes/settings/+page.svelte`:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon title="Settings" phase={4} />
```

- [ ] **Step 10.11: Verify type-check passes**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`.

- [ ] **Step 10.12: Click through every nav item in the browser**

With dev servers running, open each sidebar item and confirm it renders the ComingSoon card with the correct title and phase badge.

- [ ] **Step 10.13: Commit**

```bash
git add webui/src/routes/posts webui/src/routes/channels webui/src/routes/chats webui/src/routes/costs webui/src/routes/agent webui/src/routes/settings
git commit -m "feat(webui): skeleton routes for every IA entry (Phase 0)"
```

---

## Task 11: Home page becomes a Phase-1 skeleton

**Files:**
- Modify: `webui/src/routes/+page.svelte`

Rationale: the scaffold's working posts list lives on `/posts` territory, not `/`. Home gets a skeleton now; Phase 1 fills it with the 8-tile dashboard.

- [ ] **Step 11.1: Replace home with a skeleton**

Replace the contents of `webui/src/routes/+page.svelte` with:

```svelte
<script lang="ts">
	import ComingSoon from '$lib/components/ComingSoon.svelte';
</script>

<ComingSoon
	title="Home dashboard"
	phase={1}
	note="Phase 1 brings the 8-tile dashboard (drafts queue, scheduled, LLM cost, post views, chats heatmap, members delta, spam pings, chat graph)."
/>
```

- [ ] **Step 11.2: Confirm type-check + visual**

```bash
pnpm --dir webui run check
```

Expected: `0 ERRORS 0 WARNINGS`. Open `/` in the browser — shows the ComingSoon card titled "Home dashboard" with Phase 1 badge.

- [ ] **Step 11.3: Commit**

```bash
git add webui/src/routes/+page.svelte
git commit -m "feat(webui): home becomes Phase-1 skeleton

The scaffold's posts-list prototype was a placeholder for /. Phase 1
will build the real 8-tile dashboard in its place."
```

---

## Task 12: End-to-end verification and PR

**Files:** none.

- [ ] **Step 12.1: Full backend test run**

```bash
uv run -m pytest -x
```

Expected: all tests pass (new `tests/webapi/` included; unit suite from before unaffected).

- [ ] **Step 12.2: Lint / format / type-check**

```bash
uv run ruff check app tests && uv run ruff format app tests
uv run ty check app tests
pnpm --dir webui run check
```

Expected: each command prints clean output.

- [ ] **Step 12.3: Click-through in the browser**

With both dev servers running:

- Sidebar shows 8 items; click each — correct title in header, correct Phase badge on the Card
- Active-route highlight in the sidebar follows navigation
- `/` renders the "Home dashboard" ComingSoon card
- `curl -s http://localhost:5173/api/posts?limit=1` returns JSON (not 503)

- [ ] **Step 12.4: Push and open PR**

```bash
git push -u origin feat/web-ui-phase-0-foundation
gh pr create --title "feat(webui): Phase 0 foundation — shell + skeleton routes" --body "$(cat <<'EOF'
## Summary
- App shell (Sidebar with phase badges, Header) wraps every route
- Every IA entry (/posts, /channels, /chats, /chats/graph, /costs, /agent, /settings, plus detail routes) exists as a ComingSoon skeleton
- shadcn-svelte components installed: button, card, badge, table, skeleton, sheet, input, sonner
- require_super_admin FastAPI dep wired (no-op in dev), gates /api/posts
- openapi-typescript script (pnpm run api:sync) generates src/lib/api/types.ts
- Thin typed apiFetch wrapper in src/lib/api/client.ts

Closes Phase 0 of docs/superpowers/specs/2026-04-21-web-ui-scope-design.md.

## Test plan
- [x] uv run -m pytest tests/webapi — 2 new tests pass
- [x] pnpm --dir webui run check — 0 errors 0 warnings
- [x] ruff + ty clean
- [x] Click through every sidebar entry — correct skeleton renders
- [x] /api/posts returns JSON (not 503) with ADMIN_SUPER_ADMINS set

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Done

Phase 0 complete. Navigable shell, every route reachable, auth dep in place, type-gen working. Phase 1 plan picks this up with the home dashboard + Posts/Channels/Costs pages.
