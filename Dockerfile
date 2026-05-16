# syntax=docker/dockerfile:1.7
# Multi-stage build for optimized production image
FROM python:3.12.13-slim-trixie AS dependencies

COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files for better caching
COPY pyproject.toml uv.lock README.md ./

# Install dependencies. BuildKit cache mount keeps uv's wheel cache across
# builds even when the layer above invalidates (pyproject.toml / uv.lock
# changed) — avoids redownloading every dep from PyPI on uncached builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM node:24.15.0-alpine3.23 AS webui-dependencies

WORKDIR /app/webui

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY webui/package.json webui/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM webui-dependencies AS webui-build

COPY webui/ ./
RUN pnpm run build

# Production stage
FROM python:3.12.13-slim-trixie AS production

# Install runtime dependencies only.
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends procps && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create non-root user, logs dir, and set permissions
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup --no-create-home appuser && \
    mkdir -p /app/logs && \
    chown appuser:appgroup /app /app/logs

# Copy virtual environment from dependencies stage
COPY --from=dependencies --chown=appuser:appgroup /app/.venv /app/.venv

# Copy application source code
COPY --chown=appuser:appgroup app/ ./app/
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup --chmod=755 scripts/ ./scripts/

# Make sure we use venv
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD pgrep -f "python -m app.presentation.telegram|uvicorn app.webapi.main:app" > /dev/null || exit 1

ENTRYPOINT ["scripts/entrypoint.sh"]
CMD ["bot"]

FROM caddy:2.11.2-alpine AS webui

COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=webui-build /app/webui/build /srv

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD caddy validate --config /etc/caddy/Caddyfile >/dev/null || exit 1
