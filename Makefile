# Makefile for moderator-bot project

.PHONY: help install test lint format clean

# Default target
help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Development Setup
# ============================================================================

install: ## Install dependencies
	uv sync --dev

setup-dev: install ## Setup development environment
	uv run pre-commit install
	@echo "✅ Development environment ready!"
	@echo "Run 'make docker-dev' to start the project"

# ============================================================================
# Docker Commands
# ============================================================================

docker-dev: ## Start development environment (includes ngrok)
	docker-compose up --build

docker-prod: ## Start production environment
	docker-compose -f docker-compose.yaml up --build

docker-down: ## Stop all Docker containers
	docker-compose down

docker-clean: ## Stop containers and remove volumes
	docker-compose down -v

docker-logs: ## Show Docker logs (all services)
	docker-compose logs -f

docker-logs-bot: ## Show bot logs only
	docker-compose logs -f bot

docker-logs-api: ## Show API logs only
	docker-compose logs -f api

docker-logs-webapp: ## Show webapp logs only
	docker-compose logs -f webapp

docker-restart: ## Restart all services
	docker-compose restart

docker-restart-bot: ## Restart bot service only
	docker-compose restart bot

docker-restart-api: ## Restart API service only
	docker-compose restart api

# ============================================================================
# ngrok Integration
# ============================================================================

ngrok-url: ## Get current ngrok public URL
	@./scripts/get-ngrok-url.sh

ngrok-update-env: ## Update WEBAPP_URL in .env (optional)
	@./scripts/update-webapp-url.sh

# ============================================================================
# Code Quality
# ============================================================================

lint: ## Run linting with ruff
	uv run ruff check app tests

lint-fix: ## Fix linting issues automatically
	uv run ruff check --fix app tests

format: ## Format code with ruff
	uv run ruff format app tests

format-check: ## Check code formatting
	uv run ruff format --check app tests

type-check: ## Run type checking with mypy
	uv run mypy app tests

quality: lint format-check type-check ## Run all code quality checks

# ============================================================================
# Testing
# ============================================================================

test: ## Run all tests
	uv run pytest

test-unit: ## Run unit tests only
	uv run pytest tests/unit -v

test-integration: ## Run integration tests only
	uv run pytest tests/integration -v

test-fast: ## Run fast tests (exclude slow)
	uv run pytest -m "not slow" -v

test-cov: ## Run tests with coverage report
	uv run pytest --cov=app --cov-report=html --cov-report=term

test-watch: ## Watch files and run tests on changes
	uv run ptw --runner "pytest tests/unit tests/integration -x -q"

# ============================================================================
# Database
# ============================================================================

db-migrate: ## Create new database migration
	@read -p "Enter migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

db-upgrade: ## Apply database migrations
	uv run alembic upgrade head

db-downgrade: ## Rollback last migration
	uv run alembic downgrade -1

db-current: ## Show current migration version
	uv run alembic current

db-history: ## Show migration history
	uv run alembic history

# ============================================================================
# Local Development (without Docker)
# ============================================================================

run-bot: ## Run bot locally
	uv run -m app.presentation.telegram

run-api: ## Run FastAPI server locally
	uv run uvicorn app.presentation.api.main:app --host 0.0.0.0 --port 8000 --reload

shell: ## Open Python shell with project context
	uv run python

# ============================================================================
# CI/CD & Pre-commit
# ============================================================================

ci-test: quality test-cov ## Run full CI test suite
	@echo "✅ CI tests completed successfully!"

pre-commit: ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

# ============================================================================
# Cleanup
# ============================================================================

clean: ## Clean build artifacts and cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ .pytest_cache/ coverage.xml .mypy_cache .ruff_cache
	@echo "✅ Cleanup completed!"

clean-all: clean docker-clean ## Clean everything (code + docker)
	rm -rf .venv/ uv.lock
	@echo "✅ Full cleanup completed!"

# ============================================================================
# Debugging
# ============================================================================

debug-test: ## Run tests with verbose output
	uv run pytest -v -s --tb=long

debug-test-pdb: ## Run tests with PDB on failures
	uv run pytest --pdb

debug-logs: ## Show detailed logs from all services
	docker-compose logs --tail=100

# ============================================================================
# Security & Performance
# ============================================================================

security-check: ## Run security checks with bandit
	uv run bandit -r app/ -f json -o bandit-report.json || true
	@echo "Security check completed - see bandit-report.json"

# ============================================================================
# Utilities
# ============================================================================

version: ## Show current project version
	@echo "Version: $(shell grep version pyproject.toml | head -1 | cut -d'"' -f2)"

env-info: ## Show environment information
	@echo "Python: $(shell python --version 2>&1)"
	@echo "UV: $(shell uv --version 2>&1)"
	@echo "Docker: $(shell docker --version 2>&1)"
	@echo "Docker Compose: $(shell docker-compose --version 2>&1)"

# ============================================================================
# Combined Workflows
# ============================================================================

dev-setup: setup-dev ## Complete development setup with tests
	@echo "Running initial tests..."
	$(MAKE) test-fast
	@echo "✅ Development setup complete!"
	@echo "👉 Run 'make docker-dev' to start the project"

quick-check: lint format-check test-fast ## Quick pre-commit checks

full-check: quality test-cov ## Full quality and test suite
