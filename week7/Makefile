COMPOSE = docker compose --env-file .env -f docker-compose.yml

.PHONY: up down logs smoke warmup config

up:
	$(COMPOSE) up --build -d --wait

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

smoke:
	$(COMPOSE) run --rm --no-deps checks python /tools/smoke.py

warmup:
	$(COMPOSE) run --rm --no-deps checks python /tools/warmup.py

config:
	$(COMPOSE) config --quiet
