# Multi-stage build for optimized production image
FROM ghcr.io/astral-sh/uv:0.8.11-alpine AS dependencies

# Install system dependencies
RUN apk add --no-cache \
    postgresql-client \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers \
    protobuf-dev \
    protoc

WORKDIR /app

# Copy dependency files for better caching
COPY pyproject.toml uv.lock README.md ./

# Copy source code needed for project installation
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install production dependencies to virtual environment (includes alembic, uvicorn)
# Must copy source code BEFORE sync to properly install the project
RUN uv sync --frozen --no-dev

# Development stage
FROM ghcr.io/astral-sh/uv:0.8.11-alpine AS development

# Install system dependencies
RUN apk add --no-cache \
    postgresql-client \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers \
    protobuf-dev \
    protoc

WORKDIR /app

# Copy dependency files for better caching
COPY pyproject.toml uv.lock README.md ./

# Copy application source code BEFORE sync
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Install ALL dependencies including dev for development
# Must copy source code BEFORE sync to properly install the project
RUN uv sync --frozen

# Make uv available system-wide (symlink to /usr/local/bin) if missing
RUN [ -x /usr/local/bin/uv ] || ln -s /uv /usr/local/bin/uv

# Make sure we use venv AND uv is available
ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH"

# Make scripts executable
RUN chmod +x scripts/*.sh

# Development doesn't need to change user - keep as root for easier volume mounting

# Production stage
FROM ghcr.io/astral-sh/uv:0.8.11-alpine AS production

# Install runtime dependencies only
RUN apk add --no-cache postgresql-client

WORKDIR /app

# Copy virtual environment from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Copy application source code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Make sure we use venv AND uv is available
ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH"

# Make uv available system-wide (symlink to /usr/local/bin) if missing
RUN [ -x /usr/local/bin/uv ] || ln -s /uv /usr/local/bin/uv

# Create non-root user for security and set permissions
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup && \
    chmod +x scripts/*.sh && \
    chown -R appuser:appgroup /app

USER appuser

CMD ["python", "-m", "app.presentation.telegram"]
