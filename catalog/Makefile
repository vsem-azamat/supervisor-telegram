.DEFAULT_GOAL := help
API := .

# Port 8010, not 8000: something else on this machine already listens there,
# and a dev server that silently fails to bind is worse than one on an odd port.
API_PORT ?= 8010

.PHONY: help
help:  ## Show this list
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

# ── setup ───────────────────────────────────────────────────────────────

.PHONY: setup
setup: db-up install migrate seed demo  ## Everything needed for a first run

.PHONY: install
install:  ## Install the API's dependencies
	cd $(API) && uv sync

.PHONY: db-up
db-up:  ## Start Postgres and wait until it answers
	docker compose -f compose.dev.yml up -d db
	@until docker compose -f compose.dev.yml exec -T db pg_isready -q -U students_cz -d students_cz; \
	 do sleep 1; done
	@echo "database ready"

.PHONY: db-down
db-down:  ## Stop Postgres, keep the data
	docker compose -f compose.dev.yml down

.PHONY: db-reset
db-reset:  ## Throw the database away and rebuild it from scratch
	docker compose -f compose.dev.yml down -v
	$(MAKE) db-up migrate seed demo

.PHONY: db-shell
db-shell:  ## psql prompt
	docker compose -f compose.dev.yml exec db psql -U students_cz -d students_cz

# ── data ────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate:  ## Apply migrations
	cd $(API) && uv run alembic upgrade head

.PHONY: revision
revision:  ## Autogenerate a migration: make revision m="what changed"
	cd $(API) && uv run alembic revision --autogenerate -m "$(m)"

.PHONY: seed
seed:  ## Load reference data: subjects, institutions, service types
	cd $(API) && uv run python -m students_cz.db.seed

.PHONY: demo
demo:  ## Load plausible content so the screens have something in them
	cd $(API) && uv run python -m students_cz.db.demo

.PHONY: demo-clear
demo-clear:  ## Remove demo content, keep reference data
	cd $(API) && uv run python -m students_cz.db.demo --clear

# ── running ─────────────────────────────────────────────────────────────

.PHONY: api
api:  ## Run the API with reload
	cd $(API) && uv run uvicorn students_cz.main:app --reload --port $(API_PORT)

# ── checks ──────────────────────────────────────────────────────────────

.PHONY: test
test:  ## Run the API's tests (they need the database up)
	cd $(API) && uv run pytest -q

.PHONY: lint
lint:  ## Lint and type-check the API
	cd $(API) && uv run ruff check src tests && uv run ruff format --check src tests
	cd $(API) && uv run ty check src tests

.PHONY: format
format:  ## Reformat the API
	cd $(API) && uv run ruff check --fix src tests && uv run ruff format src tests

# Committed: the contract for clients outside this repository. See
# docs/architecture.md.
OPENAPI_DUMP := $(CURDIR)/$(API)/openapi.json

.PHONY: contract
contract:  ## Check the committed OpenAPI document is current
	@# Written beside and moved into place: a dump that fails halfway must not
	@# leave the committed document truncated.
	cd $(API) && PYTHONIOENCODING=utf-8 uv run python -m students_cz.openapi > $(OPENAPI_DUMP).tmp \
	  || { rm -f $(OPENAPI_DUMP).tmp; exit 1; }
	mv $(OPENAPI_DUMP).tmp $(OPENAPI_DUMP)
	@# An empty or broken dump would differ too, and be committed as the
	@# contract. Check it is a document before trusting the diff.
	@grep -q '"openapi"' $(OPENAPI_DUMP) || { \
	  echo "The OpenAPI dump is empty or not a document: $(OPENAPI_DUMP)"; \
	  exit 1; \
	}
	@# --porcelain and not `git diff`: a document that is new is untracked,
	@# and `git diff` cannot see those at all. Kept in a variable so a git that
	@# failed — no repository, a dubious-ownership refusal, no git at all — is
	@# not read as an empty answer, which is the same string a clean tree gives.
	@changed=$$(git status --porcelain -- $(OPENAPI_DUMP)) || { \
	  echo "git status failed; the contract check compared nothing."; \
	  exit 1; \
	}; \
	test -z "$$changed" || { \
	  echo; \
	  echo "The contract is out of date. Commit catalog/openapi.json."; \
	  git --no-pager status --short -- $(OPENAPI_DUMP); \
	  exit 1; \
	}

.PHONY: check
check: lint test contract  ## Everything CI would run
