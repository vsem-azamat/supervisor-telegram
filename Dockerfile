# Multi-stage build with Debian for faster wheel installs
FROM ghcr.io/astral-sh/uv:0.8.11-python3.12-bookworm-slim AS dependencies

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files for better caching
COPY pyproject.toml uv.lock README.md ./

# Copy source code needed for project installation
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install production dependencies (uses prebuilt wheels - fast!)
RUN uv sync --frozen --no-dev

# Development stage - optimized for volume mounts
FROM ghcr.io/astral-sh/uv:0.8.11-python3.12-bookworm-slim AS development

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only copy dependency files - code comes via volume mount
COPY pyproject.toml uv.lock README.md ./

# Create minimal package structure for uv sync
RUN mkdir -p app && touch app/__init__.py

# Install all dependencies including dev (uses prebuilt wheels - fast!)
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

# Production stage
FROM ghcr.io/astral-sh/uv:0.8.11-python3.12-bookworm-slim AS production

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from dependencies stage
COPY --from=dependencies /app/.venv /app/.venv

# Copy application source code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

ENV PATH="/app/.venv/bin:$PATH"

# Create non-root user for security
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup appuser && \
    chmod +x scripts/*.sh && \
    chown -R appuser:appgroup /app

USER appuser

CMD ["python", "-m", "app.presentation.telegram"]
