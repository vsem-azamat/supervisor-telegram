#!/bin/sh
set -e

python - <<'PY'
import asyncio
import os
import sys

import asyncpg


async def main() -> int:
    host = os.getenv("DB_HOST", "db")
    port = int(os.getenv("DB_PORT", "5432"))
    max_attempts = int(os.getenv("POSTGRES_WAIT_ATTEMPTS", "60"))

    for attempt in range(1, max_attempts + 1):
        try:
            conn = await asyncpg.connect(
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"],
                database=os.environ["DB_NAME"],
                host=host,
                port=port,
                timeout=5,
            )
            await conn.close()
            return 0
        except Exception as exc:
            if attempt >= max_attempts:
                print(f"Postgres still not reachable after {attempt} attempts: {exc}", file=sys.stderr)
                return 1
            print(f"Waiting for Postgres at {host}:{port}...")
            await asyncio.sleep(1)

    return 1


raise SystemExit(asyncio.run(main()))
PY
