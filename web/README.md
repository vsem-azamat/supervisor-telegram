# Students CZ — Mini App

The Telegram Mini App front end for the student help catalog. Talks to the
FastAPI service in [`apps/api`](../api).

## Stack

| Concern      | Choice                                            |
| ------------ | ------------------------------------------------- |
| Build        | Vite 8, `@vitejs/plugin-react` (oxc)              |
| UI           | React 19                                          |
| Telegram     | `@tma.js/sdk-react` 3                             |
| Data         | TanStack Query 5                                  |
| Routing      | React Router 8                                    |
| i18n         | Lingui 6 — `ru`, `cs`, `en`, `uk`                 |
| Lint, format | Biome 2                                           |
| Packages     | pnpm 11                                           |

Two things this project deliberately does **not** have:

- **No UI kit and no webfonts.** System font only, no CDN, no external
  requests. The interface is themed entirely from Telegram's own CSS variables
  so it matches whatever client it is opened in.
- **No `telegram-web-app.js`.** The official script and `@tma.js` both claim
  the same bridge and conflict. The SDK is the only thing talking to Telegram.

## Getting started

```sh
pnpm install
pnpm dev
```

The API is expected at `http://127.0.0.1:8010` — see the note in
`vite.config.ts` about what holds 8000 — and `/api` and `/healthz` are
proxied there, so calls from the browser stay same-origin. Start it separately,
or with `make api` from the repository root:

```sh
cd ../api && uv run uvicorn students_cz.main:app --reload --port 8010
```

### HTTPS is not optional

Telegram refuses to load a Mini App over plain HTTP, so the dev server runs
over TLS via `vite-plugin-mkcert`. On the very first run mkcert downloads
itself and installs a local certificate authority, which needs `sudo`:

```
ERROR: failed to execute "tee": exit status 1
sudo: a password is required
```

Run the install once, by hand, in a terminal that can prompt you:

```sh
~/.vite-plugin-mkcert/mkcert -install
```

After that `pnpm dev` serves `https://localhost:5173` with a certificate your
browser trusts, and every later run is silent.

If you cannot use `sudo` — CI, a locked-down machine — fall back to HTTP:

```sh
VITE_NO_HTTPS=1 pnpm dev
```

That is enough to work on components in a desktop browser, but Telegram will
not load the app, so it cannot be used to test inside the client.

## Working outside Telegram

Opened in a normal browser there are no launch parameters, so the SDK cannot
initialise and nothing renders. `src/mockEnv.ts` substitutes a plausible
Telegram environment; it is imported only under `import.meta.env.DEV` and is
tree-shaken out of production builds.

The mock's init data is **unsigned**, so the API will reject it with 401. That
is correct behaviour, not a bug. To exercise real endpoints either open the app
through Telegram, or capture a real init data query string from a Mini App
session signed with the same bot token the API runs with and put it in
`.env.local`:

```sh
cp .env.example .env.local
# then set VITE_MOCK_INIT_DATA=<raw init data>
```

Change `MOCK_USER.language_code` in `src/mockEnv.ts` to check the other three
interface languages.

## Debugging on a phone

1. Start the dev server. It listens on every interface, so the `Network:` URL
   it prints is reachable from a phone on the same Wi-Fi.
2. Point your bot's Mini App URL at that address —
   [@BotFather](https://t.me/BotFather) → *Bot Settings* → *Menu Button*. A
   second, development-only bot is worth having so you never repoint the real
   one.
3. Open the Mini App. [eruda](https://github.com/liriliri/eruda) loads
   automatically in development and gives you a console, a network log and a
   DOM inspector on the device itself — which beats a cable and a Mac.

The phone must trust the mkcert CA to load the page. The simplest way around
that is a tunnel with a real certificate (`cloudflared tunnel --url
https://localhost:5173`) and pointing BotFather at the tunnel URL instead.

Telegram caches Mini App assets aggressively. If a change refuses to appear,
close the app from the client's menu rather than just backing out of it.

## Scripts

| Script                | What it does                                          |
| --------------------- | ----------------------------------------------------- |
| `pnpm dev`            | Dev server on `https://localhost:5173`, host exposed  |
| `pnpm build`          | Typecheck, then production build into `dist/`         |
| `pnpm preview`        | Serve `dist/` locally                                 |
| `pnpm lint`           | Biome — lint, format check and import order           |
| `pnpm lint:fix`       | The same, with the safe fixes applied                 |
| `pnpm format`         | Format only                                           |
| `pnpm typecheck`      | `tsc -b`, then the tests' own project, no emit         |
| `pnpm test`           | `tests/` on node's own runner; fails if it finds none  |
| `pnpm i18n:extract`   | Scan source for new messages, update the `.po` files  |
| `pnpm i18n:compile`   | Compile catalogs by hand (the build does not need it) |
| `pnpm api:generate`   | Regenerate API types — via `make contract`, see below  |

## Layout

```
src/
  main.tsx           startup: mock env, SDK, locale, render
  mockEnv.ts         fake Telegram environment, DEV only
  router.tsx         routes
  Root.tsx           shell; binds the Telegram back button to the router
  index.css          reset and Telegram CSS variables — nothing else
  hooks/useTelegram  theme, safe area, back button, main button
  lib/api.ts         fetch client; adds `Authorization: tma <initData>`
  lib/types.ts       hand-written mirrors of the API schemas
  i18n/              locale resolution and lazy catalog loading
  locales/{ru,cs,en,uk}/messages.po
  pages/             route components (placeholders for now)
```

### Styling

`src/index.css` is a reset plus the wiring for Telegram's runtime CSS
variables, and that is all it should ever be. Component styles belong with
their components. The variables — `--tg-theme-*`, `--tg-viewport-*`,
`--tg-viewport-safe-area-inset-*` — only exist once the SDK has mounted, so
always give them a fallback:

```css
color: var(--tg-theme-text-color, #000000);
```

`index.html` sets `viewport-fit=cover`; without it the safe-area insets are
always zero and the layout will not clear the notch.

### Translations

Only interface chrome lives in the catalogs. Names of subjects, faculties and
service types are translated in the database and arrive from the API already
localised — never put them through Lingui.

The API also returns `Phrase` objects (`{code, params}`) instead of finished
sentences, precisely so plural agreement happens here, where the CLDR rules
are, rather than in a Python service that would have to reimplement them.

Write messages with the macros, then extract:

```tsx
import { Trans, useLingui } from '@lingui/react/macro';
```

```sh
pnpm i18n:extract
```

`ru` is the source locale, so its translations are filled in automatically.
The `.po` files are the source of truth and are committed; the compiled output
is generated at build time by `@lingui/vite-plugin` and is not.

The startup locale comes from the Telegram user's `language_code`, normalised
(`en-US` → `en`, unknown → `ru`, and the legacy `cz`/`ua` → `cs`/`uk`). A
choice the user makes by hand is stored in `localStorage` and outranks it.

### API types

`src/lib/generated/` holds types generated from the API's OpenAPI document, and
it is **committed**. `src/lib/types.ts` still declares the rest of the wire by
hand and must be kept in step with `apps/api/src/students_cz/schemas.py`; a type
moves across as the screen using it is touched.

To regenerate, run `make contract` from the repository root and commit what it
writes. It needs no server: the document is dumped straight from the app. The
same target is what CI runs, and it fails when the committed copy differs — so a
schema changed without regenerating stops being something only the next runtime
error tells you about.

Do not generate from a running API. Given a URL, the generator writes it into
the client as a literal type — `ClientOptions.baseUrl: 'http://127.0.0.1:8010'`
instead of the URL-independent form — so the result carries whichever machine
produced it, and the contract check rejects it. Reading the document from a file
has no URL to bake in, which is why `make contract` dumps it. There is no
default input for that reason: `pnpm api:generate` on its own says so and stops.

Generation is not wired into `pnpm build` on purpose — a build that fails
because a backend is not running is a bad build. The directory is excluded from
Biome, since the generator owns its formatting.
