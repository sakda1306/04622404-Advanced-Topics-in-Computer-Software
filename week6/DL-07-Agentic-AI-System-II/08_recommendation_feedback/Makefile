.PHONY: up down logs rebuild test test-integration ps

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose up -d --build

ps:
	docker compose ps

# Unit tests only (no DB/Redis required)
test:
	docker compose exec app pytest tests/test_recommendation.py -v

# Integration tests against the real Postgres/Redis started by `make up`
test-integration:
	docker compose exec app pytest tests/test_db_integration.py -v
