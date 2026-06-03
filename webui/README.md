# Konnekt admin web UI

SvelteKit + Tailwind + FastAPI admin panel.

## Stack

- **Frontend**: SvelteKit 2 (Svelte 5, TS) + Tailwind v4 — served by Vite on **:5174**
- **Backend**: FastAPI + SQLAlchemy (shares `app.db.models` with the bot) — served by uvicorn on **:8787**
- **Production/edge dev**: web UI and FastAPI share one public origin; `/api/*` proxies to FastAPI and all other routes serve the web UI
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
# → http://localhost:5174
```

Vite proxies `/api/*` → `:8787`, so the browser hits a single origin locally too.
Remote dev may expose Vite through the edge proxy for native browser testing,
but `/api/*` must still be routed by the edge directly to FastAPI.

## Browser contract tests

```bash
pnpm --dir webui run test:e2e
```

The Playwright suite starts Vite on `127.0.0.1:5174` and mocks API responses
that are unrelated to the browser contract under test.

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
