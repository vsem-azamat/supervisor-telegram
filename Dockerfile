# Multi-stage build for optimized production image
FROM ghcr.io/astral-sh/uv:0.8.11-alpine AS dependencies

# Install system dependencies
RUN apk add --no-cache \
    postgresql-client \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers \
    protobuf-dev

WORKDIR /app

# Copy dependency files for better caching
COPY pyproject.toml uv.lock README.md ./

# Install dependencies to virtual environment
RUN uv sync --frozen --no-dev

# Development stage
FROM ghcr.io/astral-sh/uv:0.8.11-alpine AS development

# Install system dependencies
RUN apk add --no-cache \
    postgresql-client \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers

WORKDIR /app

# Copy dependency files for better caching
COPY pyproject.toml uv.lock README.md ./

# Install ALL dependencies including dev for development
RUN uv sync --frozen

# Copy application source code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Make sure we use venv
ENV PATH="/app/.venv/bin:$PATH"

# Make scripts executable
RUN chmod +x scripts/*.sh

# Development doesn't need to change user - keep as root for easier volume mounting

# Production stage
FROM python:3.12-alpine AS production

# Install runtime dependencies only
RUN apk add --no-cache postgresql-client procps

WORKDIR /app

# Copy virtual environment from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Copy application source code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Make sure we use venv
ENV PATH="/app/.venv/bin:$PATH"

# Create non-root user, logs dir, and set permissions
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup && \
    chmod +x scripts/*.sh && \
    mkdir -p /app/logs && \
    chown -R appuser:appgroup /app

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD pgrep -f "python -m app.presentation.telegram" > /dev/null || exit 1

ENTRYPOINT ["scripts/entrypoint.sh"]
