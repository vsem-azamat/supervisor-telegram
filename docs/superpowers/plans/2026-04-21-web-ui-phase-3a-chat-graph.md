# Phase 3a — Chat Graph Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans (or do it inline). Each task ends with a commit.

**Goal:** Replace the home `Chat graph` skeleton + the `/chats/graph` ComingSoon stub with a working tree viewer of parent → child chat relationships.

**Architecture:** One self-FK column on `Chat` (`parent_chat_id`) + free-text `relation_notes`. New `GET /api/chats/graph` returns roots with nested children. FE renders a collapsible nested list. No graph library — tree is enough per spec ("Tree over graph").

**Tech Stack:** SQLAlchemy 2.x async, Alembic, FastAPI, SvelteKit 2 + Svelte 5 runes, Tailwind v4.

---

## File Structure

| Path | Purpose |
|---|---|
| `alembic/versions/<new>_add_chat_parent_chat_id.py` | Migration: add `parent_chat_id` + `relation_notes` |
| `app/db/models.py` | Extend `Chat` with `parent_chat_id`, `relation_notes`, optional `parent`/`children` relationships |
| `app/webapi/schemas.py` | Add `ChatNode` (id, title, member_count, children, relation_notes) |
| `app/webapi/routes/chats.py` | New `GET /chats/graph`; extend list + detail responses with `parent_chat_id` |
| `webui/src/routes/chats/graph/+page.svelte` | Replace ComingSoon → collapsible tree |
| `webui/src/lib/components/chat/ChatTreeNode.svelte` | Recursive tree-row component |
| `webui/src/routes/chats/[id]/+page.svelte` | Show parent link + children list card |
| `webui/src/routes/+page.svelte` | Replace `Chat graph` SkeletonTile with live mini-tree (depth ≤ 2) |
| `tests/unit/test_chat_parent_relationship.py` | ORM-level: parent/children navigation |
| `tests/webapi/test_chats_graph.py` | API: tree shape, orphans, cycle protection |

---

## Tasks

### Task 1 — Migration: `parent_chat_id` + `relation_notes`

**Files:**
- Create: `alembic/versions/b1c2d3e4f5a6_add_chat_parent.py`

```python
"""Add chat parent_chat_id + relation_notes.

Self-referencing FK lets us model the ČVUT → faculty → department tree
without a separate join table. Single column, nullable for roots.

Revision ID: b1c2d3e4f5a6
Revises: a2b3c4d5e6f7
Create Date: 2026-04-21 22:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chats",
        sa.Column("parent_chat_id", sa.BigInteger(), sa.ForeignKey("chats.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("chats", sa.Column("relation_notes", sa.String(), nullable=True))
    op.create_index("ix_chats_parent_chat_id", "chats", ["parent_chat_id"])


def downgrade() -> None:
    op.drop_index("ix_chats_parent_chat_id", table_name="chats")
    op.drop_column("chats", "relation_notes")
    op.drop_column("chats", "parent_chat_id")
```

Commit: `feat(db): add Chat.parent_chat_id + relation_notes migration`

### Task 2 — ORM update + relationship

**Files:**
- Modify: `app/db/models.py` (Chat class)

Add fields + relationships:
```python
parent_chat_id: Mapped[int | None] = mapped_column(
    BigInteger, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True, index=True
)
relation_notes: Mapped[str | None] = mapped_column(String, nullable=True)

parent: Mapped["Chat | None"] = relationship(
    "Chat", remote_side="Chat.id", back_populates="children", lazy="joined"
)
children: Mapped[list["Chat"]] = relationship(
    "Chat", back_populates="parent", cascade="save-update, merge"
)
```

Extend `__init__` to accept `parent_chat_id` and `relation_notes` (optional).

**Test (`tests/unit/test_chat_parent_relationship.py`):**
- root chat (parent_chat_id=None) → `chat.children == [child1, child2]`
- child.parent.id == root.id
- deleting root sets children's parent_chat_id to None (FK ondelete=SET NULL)

Commit: `feat(db): chat parent/children relationship`

### Task 3 — Schema: `ChatNode`

**Files:**
- Modify: `app/webapi/schemas.py`

```python
class ChatNode(BaseModel):
    id: int
    title: str | None
    member_count: int | None = None
    relation_notes: str | None = None
    children: list["ChatNode"] = []

ChatNode.model_rebuild()
```

Also extend `ChatRead` and `ChatDetail` with `parent_chat_id: int | None`, `relation_notes: str | None`.

(Phase 3a doesn't enrich tree nodes with member_count to avoid Telethon fan-out on every page load; `member_count` stays default `None` for the tree endpoint; list/detail endpoints keep their existing enrichment.)

### Task 4 — API: `GET /api/chats/graph`

**Files:**
- Modify: `app/webapi/routes/chats.py`

Add route, just under `list_chats`:

```python
@router.get("/graph", response_model=list[ChatNode])
async def get_chat_graph(
    session: Annotated[AsyncSession, Depends(get_session)],
    _admin_id: Annotated[int, Depends(require_super_admin)],
) -> list[ChatNode]:
    chats = (await session.execute(select(Chat))).scalars().all()
    by_id = {c.id: ChatNode(id=c.id, title=c.title, relation_notes=c.relation_notes, children=[]) for c in chats}
    roots: list[ChatNode] = []
    for c in chats:
        node = by_id[c.id]
        parent_id = c.parent_chat_id
        if parent_id is not None and parent_id in by_id and parent_id != c.id:
            by_id[parent_id].children.append(node)
        else:
            roots.append(node)
    # stable order: title, then id
    def _key(n: ChatNode) -> tuple:
        return (n.title or "", n.id)
    def _sort(nodes: list[ChatNode]) -> None:
        nodes.sort(key=_key)
        for n in nodes:
            _sort(n.children)
    _sort(roots)
    return roots
```

**IMPORTANT:** declare this route **before** `@router.get("/{chat_id}")` so `/graph` doesn't get matched as a chat_id.

Also add `parent_chat_id` and `relation_notes` to the existing `ChatRead`/`ChatDetail` build sites.

**Tests (`tests/webapi/test_chats_graph.py`):**
- empty DB → `[]`
- 1 root + 2 children → 1 element with 2 children
- orphan child (parent_chat_id points to nonexistent) → orphan becomes a root
- self-reference (parent_chat_id == id) → treated as root, not infinite loop

Commit: `feat(webapi): chat graph endpoint + parent fields on chat read/detail`

### Task 5 — Run `pnpm run api:sync`

After task 4 backend lives, regenerate FE types:
```bash
cd webui && pnpm run api:sync
```
Confirm `ChatNode` appears in `webui/src/lib/api/types.ts`.

### Task 6 — FE: recursive `ChatTreeNode` component

**Files:**
- Create: `webui/src/lib/components/chat/ChatTreeNode.svelte`

```svelte
<script lang="ts">
  import { goto } from '$app/navigation';
  import type { components } from '$lib/api/types';
  type Node = components['schemas']['ChatNode'];
  type Props = { node: Node; depth?: number };
  let { node, depth = 0 }: Props = $props();
  let expanded = $state(depth < 2);
</script>

<li class="space-y-1">
  <div class="flex items-center gap-2">
    {#if node.children.length > 0}
      <button class="text-xs text-zinc-500 hover:text-zinc-900"
              onclick={() => (expanded = !expanded)}>
        {expanded ? '▾' : '▸'}
      </button>
    {:else}
      <span class="w-3"></span>
    {/if}
    <button class="truncate text-sm text-zinc-800 hover:underline"
            onclick={() => goto(`/chats/${node.id}`)}>
      {node.title ?? `#${node.id}`}
    </button>
    {#if node.relation_notes}
      <span class="text-xs text-zinc-400">· {node.relation_notes}</span>
    {/if}
  </div>
  {#if expanded && node.children.length > 0}
    <ul class="ml-4 space-y-1 border-l border-zinc-200 pl-2">
      {#each node.children as child (child.id)}
        <ChatTreeNode node={child} depth={depth + 1} />
      {/each}
    </ul>
  {/if}
</li>
```

### Task 7 — FE: `/chats/graph` page

**Files:**
- Modify: `webui/src/routes/chats/graph/+page.svelte`

Replace ComingSoon with:
```svelte
<script lang="ts">
  import * as Card from '$lib/components/ui/card/index.js';
  import ChatTreeNode from '$lib/components/chat/ChatTreeNode.svelte';
  import { useLivePoll } from '$lib/hooks/useLivePoll.svelte';
  import type { components } from '$lib/api/types';
  type Tree = components['schemas']['ChatNode'][];
  const tree = useLivePoll<Tree>('/api/chats/graph', 60_000);
</script>

<div class="mx-auto max-w-3xl space-y-4 px-6 py-6">
  <header class="flex items-baseline justify-between">
    <h2 class="text-lg font-semibold tracking-tight">Chat graph</h2>
    {#if tree.lastUpdatedAt}<span class="text-xs text-zinc-500">Updated {tree.lastUpdatedAt.toLocaleTimeString()}</span>{/if}
  </header>
  <Card.Root>
    <Card.Content class="py-4">
      {#if tree.loading}<p class="text-sm text-zinc-500">Loading…</p>
      {:else if tree.error}<p class="text-sm text-red-600">Error: {tree.error}</p>
      {:else if !tree.data || tree.data.length === 0}
        <p class="text-sm text-zinc-500">No relationships defined yet. Set <code>parent_chat_id</code> on chats to build the tree.</p>
      {:else}
        <ul class="space-y-1">
          {#each tree.data as root (root.id)}<ChatTreeNode node={root} />{/each}
        </ul>
      {/if}
    </Card.Content>
  </Card.Root>
</div>
```

### Task 8 — FE: chat detail shows parent + children

**Files:**
- Modify: `webui/src/routes/chats/[id]/+page.svelte`

Add a "Relationships" Card after Overview, only if `parent_chat_id` or children exist. Children list comes from filtering the graph endpoint client-side, OR (simpler) we extend `ChatDetail` to include `children: list[ChatNode]` server-side.

**Decision:** server-side. Add to `get_chat` route:
```python
children_rows = (await session.execute(
    select(Chat).where(Chat.parent_chat_id == chat_id)
)).scalars().all()
children_nodes = [ChatNode(id=c.id, title=c.title, relation_notes=c.relation_notes, children=[]) for c in children_rows]
```
And include `children=children_nodes`, `parent_chat_id=chat.parent_chat_id`, `relation_notes=chat.relation_notes` in `ChatDetail`.

FE card:
```svelte
{#if detail.data.parent_chat_id !== null || detail.data.children.length > 0}
  <Card.Root>
    <Card.Header><Card.Title class="text-sm">Relationships</Card.Title></Card.Header>
    <Card.Content class="space-y-2 text-sm">
      {#if detail.data.parent_chat_id !== null}
        <div>Parent: <a href="/chats/{detail.data.parent_chat_id}" class="underline">#{detail.data.parent_chat_id}</a></div>
      {/if}
      {#if detail.data.children.length > 0}
        <div>
          Children:
          <ul class="ml-4 list-disc">
            {#each detail.data.children as c (c.id)}
              <li><a href="/chats/{c.id}" class="underline">{c.title ?? '#' + c.id}</a></li>
            {/each}
          </ul>
        </div>
      {/if}
    </Card.Content>
  </Card.Root>
{/if}
```

### Task 9 — Home tile: live mini-tree

**Files:**
- Modify: `webui/src/routes/+page.svelte`

Replace `<SkeletonTile title="Chat graph" phase={3} />` with:
```svelte
<div class="md:col-span-2 xl:col-span-2">
  <Tile title="Chat graph (preview)">
    {#if treeRoots.length === 0}
      <p class="text-xs text-zinc-500">No relationships yet.</p>
    {:else}
      <ul class="space-y-1">
        {#each treeRoots.slice(0, 3) as root (root.id)}<ChatTreeNode node={root} depth={1} />{/each}
      </ul>
      <a href="/chats/graph" class="mt-2 inline-block text-xs text-zinc-500 hover:underline">View full tree →</a>
    {/if}
  </Tile>
</div>
```

Tree data fetched via a second `useLivePoll<ChatNode[]>('/api/chats/graph', 120_000)`.

Adjust the trailing skeleton row (only Spam pings remains there, give it `xl:col-span-2`).

### Task 10 — Smoke + commit + PR

```bash
uv run alembic upgrade head
uv run -m pytest tests/unit/test_chat_parent_relationship.py tests/webapi/test_chats_graph.py tests/webapi/test_chats.py -x
ruff check app tests && ruff format --check app tests
ty check app
cd webui && pnpm run check
```

Branch: `webui/phase-3a-chat-graph`. Single PR squashed into main.

---

## Self-Review Notes

- **Spec coverage:** parent_chat_id + relation_notes ✅; nested list viewer ✅; tree (not graph) ✅. Spam detector + agent chat are out of scope (3b, 3c).
- **Migration safety:** column is nullable, no backfill needed. FK uses `ondelete=SET NULL` so deleting a parent doesn't cascade-delete children.
- **Cycle protection:** in `get_chat_graph`, `parent_id != c.id` check prevents self-loop. Multi-hop cycles (a→b→a) are not detectable in one pass — left as future hardening; in practice admins won't create cycles by accident, and `parent_chat_id` is admin-only via DB until Phase 4 mutations land.
- **Telethon load:** tree endpoint deliberately does NOT enrich nodes with member_count to avoid N+1 RPCs on every poll.
- **Route ordering:** `/graph` must be before `/{chat_id}` in the router or it gets shadowed.
- **No mutation surface yet:** parent_chat_id is set via DB / future Phase 4 admin UI. Phase 3a is read-only.
