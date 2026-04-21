# Konnekt admin web UI

SvelteKit + Tailwind + FastAPI admin panel. Dev-mode scaffold only — no auth, no Docker.

## Stack

- **Frontend**: SvelteKit 2 (Svelte 5, TS) + Tailwind v4 — served by Vite on **:5173**
- **Backend**: FastAPI + SQLAlchemy (shares `app.db.models` with the bot) — served by uvicorn on **:8787**
- **UI kit**: shadcn-svelte configured via `components.json`. Add components with
  `pnpm dlx shadcn-svelte@latest add <name>` (runs interactively — use a real terminal).

## Run in dev mode

Two terminals.

```bash
# Terminal 1 — API
uv run -m app.webapi
# → http://127.0.0.1:8787/api/health
# → http://127.0.0.1:8787/api/docs (Swagger)

# Terminal 2 — frontend
pnpm --dir webui run dev
# → http://localhost:5173
```

Vite proxies `/api/*` → `:8787`, so the browser hits a single origin.

## Type check

```bash
pnpm --dir webui run check
```

## Layout

```
app/webapi/          FastAPI backend
├── main.py          app factory + CORS
├── deps.py          get_session DI
├── schemas.py       Pydantic response models
└── routes/          endpoints (health, posts)

webui/
├── src/routes/      pages
├── src/lib/         utils.ts (cn helper), components/ (shadcn target)
└── vite.config.ts   proxy → :8787
```
