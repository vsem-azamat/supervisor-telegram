# Catalog

The API behind the Mini App's help screens: helpers and their offers, search,
requests, the partner cards, and what the console reads about them. FastAPI
on its own PostgreSQL, served under `/api/v1/*` on the app's origin.

It is a separate Python project from the bot and webapi around it: its own
`pyproject.toml`, lockfile, migrations and database. The rules it keeps are in
[`docs/`](docs/) — [architecture](docs/architecture.md),
[data model](docs/data-model.md), [deployment](docs/deploy.md) — and
`openapi.json` is the contract `web/` generates its client from.

```sh
make setup   # database, dependencies, migrations, reference data, demo content
make api     # http://127.0.0.1:8010
make test lint contract
```

It came from the `teachers-catalog` repository on 30 September 2026; the
history before that is there.
