.PHONY: help dev dev-ngrok dev-remote down logs install setup-dev lint lint-fix format test test-cov db-migrate db-upgrade clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# Development
dev: ## Local dev with full hot reload (open localhost:8080)
	docker compose --profile local up --build

dev-ngrok: ## Telegram Mini App testing via ngrok (bot/api hot reload, webapp bundled)
	docker compose -f docker-compose.yaml -f docker-compose.ngrok.yml --profile local up --build --remove-orphans

dev-remote: ## Start dev with remote DB (.env.prod-db)
	docker compose --env-file .env --env-file .env.prod-db up --build

down: ## Stop all containers
	docker compose -f docker-compose.yaml --profile local down --remove-orphans

logs: ## Show logs (usage: make logs or make logs s=bot)
	docker compose logs -f $(s)

# Setup
install: ## Install dependencies
	uv sync --dev

setup-dev: install ## Setup dev environment
	uv run pre-commit install

# Code Quality
lint: ## Run linter
	uv run ruff check app tests

lint-fix: ## Fix lint issues
	uv run ruff check --fix app tests

format: ## Format code
	uv run ruff format app tests

test: ## Run tests
	uv run pytest

test-cov: ## Run tests with coverage
	uv run pytest --cov=app --cov-report=html --cov-report=term

# Database
db-migrate: ## Create migration
	@read -p "Message: " msg; uv run alembic revision --autogenerate -m "$$msg"

db-upgrade: ## Apply migrations
	docker compose exec bot uv run alembic upgrade head

# Cleanup
clean: ## Clean cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache .ruff_cache
