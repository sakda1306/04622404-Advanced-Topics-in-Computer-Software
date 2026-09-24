UV ?= uv
COMPOSE ?= docker compose

.PHONY: install up down logs ps migrate downgrade revision seed token scenario test test-unit test-api \
	test-integration test-e2e test-fast cov lint format typecheck check openapi

install:
	$(UV) sync

up:
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api worker beat

ps:
	$(COMPOSE) ps

migrate:
	$(COMPOSE) run --rm migrate

downgrade:
	$(COMPOSE) run --rm migrate alembic downgrade -1

revision:
	$(UV) run alembic revision -m "$(m)"

token:
	$(COMPOSE) exec api python -m scripts.dev_token

scenario:
	curl -s -X PUT -H "content-type: application/json" -d '{"name":"$(s)"}' http://localhost:8010/_mock/scenario

seed:
	$(COMPOSE) run --rm migrate python -m scripts.seed_reference_data

test:
	$(UV) run pytest

test-unit:
	$(UV) run pytest tests/unit

test-api:
	$(UV) run pytest tests/api

test-integration:
	$(UV) run pytest tests/integration

test-e2e:
	E2E_BASE_URL=http://localhost:8000 E2E_MOCK_AGENT_URL=http://localhost:8010 $(UV) run pytest -m e2e tests/e2e

test-fast:
	$(UV) run pytest -m "not integration"

cov:
	$(UV) run pytest --cov --cov-report=term-missing

lint:
	$(UV) run ruff format --check .
	$(UV) run ruff check .

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:
	$(UV) run mypy app tests migrations scripts

openapi:
	$(UV) run python -m scripts.export_openapi

check: lint typecheck test
