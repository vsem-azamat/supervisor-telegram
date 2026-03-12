#!/bin/sh
set -e

echo "Running entrypoint..."

# Wait for remote PostgreSQL to be ready
./scripts/wait_for_postgres.sh

# Run database migrations
echo "Running Alembic migrations..."
alembic upgrade head

# Start the bot as PID 1
echo "Starting bot..."
exec python -m app.presentation.telegram
