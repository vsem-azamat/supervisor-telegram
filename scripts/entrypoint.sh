#!/bin/sh
set -e

# Ensure venv is on PATH (set in Dockerfile but not always inherited by sh)
export PATH="/app/.venv/bin:$PATH"

echo "Running entrypoint..."

# Wait for remote PostgreSQL to be ready
./scripts/wait_for_postgres.sh

case "${1:-bot}" in
  bot)
    # Run database migrations before starting the primary worker.
    echo "Running Alembic migrations..."
    alembic upgrade head

    echo "Starting bot..."
    exec python -m app.presentation.telegram
    ;;
  webapi)
    echo "Starting webapi..."
    exec uvicorn app.webapi.main:app --host 0.0.0.0 --port 8787
    ;;
  *)
    exec "$@"
    ;;
esac
