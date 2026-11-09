# 00 — Overview

> Path convention for all files in this folder: paths are relative to `DL-07-Agentic-AI-System-II/` unless they start with `/` (repo root). Example: `02_api_backend/app/main.py:33`.

## What the project does

A Thai/English **travel safety assistant**. A user enters origin, destination and departure time. The system gathers live weather, transport and disaster data, scores route risk, retrieves approved emergency guidance, picks one action with deterministic rules (`TRAVEL_NORMALLY`, `CHANGE_ROUTE`, `DELAY_TRAVEL`, `AVOID_TRAVEL`) and returns an explained recommendation with sources, data freshness and degraded-service warnings (`README.md`, `02_api_backend/app/schemas/v1/travel.py:214`).

Key design rule: **safety decisions are deterministic; the LLM may only explain a locked decision** (`README.md` "Summary", `07_decision_llm_engine/decision_engine/explanation.py:64`).

## Maturity per module (important for reuse)

| Module | Folder | State in code |
|---|---|---|
| 01 Web app | `01_web_app/` | Next.js single page + status/admin pages, real API client, mock fallback |
| 02 API backend | `02_api_backend/` | Most complete: FastAPI + Celery + Postgres/PostGIS + Redis + MinIO, ~150 tests, CI |
| 03 Travel agent | `03_travel_ai_agent/` | Rule-based orchestrator (no LLM planner yet: `travel_agent/config.py:9`) |
| 04 External data | `04_external_data_services/` | Plain-function adapters (Open-Meteo, TomTom, GDACS), no service/cache |
| 05 Data integration | `05_data_integration/` | One `build_context()` function (`integration.py:387`) |
| 06 Risk + knowledge | `06_risk_knowledge_services/` | Rule-based risk, BM25 retrieval, no corpus bundled, no vector DB |
| 07 Decision + LLM | `07_decision_llm_engine/` | Versioned policy + template explanation; LLM seam exists, **no LLM provider wired** |
| 08 Recommendation/feedback | `08_recommendation_feedback/` | Separate FastAPI + Postgres + Redis prototype, overlaps with 02 |

## Tech stack (resolved versions from lock files)

| Layer | Package | Version | Source |
|---|---|---|---|
| Python | CPython | 3.12 | `02_api_backend/Dockerfile:4`, `pyproject.toml` `requires-python` |
| API | fastapi | 0.141.1 | `02_api_backend/uv.lock` |
| API | uvicorn | 0.53.0 | `02_api_backend/uv.lock` |
| Validation | pydantic / pydantic-settings | 2.13.5 / 2.15.0 | `02_api_backend/uv.lock` |
| DB | sqlalchemy (async) / asyncpg / alembic / geoalchemy2 | 2.0.54 / 0.31.0 / 1.20.0 / 0.20.0 | `02_api_backend/uv.lock` |
| Queue | celery[redis] | 5.6.3 | `02_api_backend/uv.lock` |
| Cache/state | redis (py) | 6.4.0 | `02_api_backend/uv.lock` |
| HTTP client | httpx | 0.28.1 | `02_api_backend/uv.lock` |
| Retries (agent→07) | tenacity | 9.1.4 | `03_travel_ai_agent/uv.lock` |
| JWT | joserfc | 1.7.5 | `02_api_backend/uv.lock` |
| Crypto | cryptography | 50.0.1 | `02_api_backend/uv.lock` |
| Logging | structlog | 26.1.0 | `02_api_backend/uv.lock` |
| Tracing/metrics | opentelemetry-sdk / prometheus-client | 1.44.0 / 0.26.0 | `02_api_backend/uv.lock` |
| Object store | minio (py) | 7.2.20 | `02_api_backend/uv.lock` |
| Templates (07) | jinja2 | 3.1.6 | `07_decision_llm_engine/uv.lock` |
| Tests | pytest / testcontainers | 9.1.1 / 4.15.0 | `02_api_backend/uv.lock` |
| Frontend | next / react / typescript | 15.5.25 / 19.3.0 / 5.9.3 | `01_web_app/package-lock.json` |
| Frontend | @tanstack/react-query / zod / react-hook-form | 5.103.1 / 3.25.76 / 7.88.0 | `01_web_app/package-lock.json` |
| Frontend | tailwindcss / leaflet | 3.4.19 / 1.9.4 | `01_web_app/package-lock.json` |
| Infra images | postgis/postgis:16-3.4, redis:7-alpine, quay.io/minio/minio, keycloak 26.7.4, jaeger 2.10.0 | — | `02_api_backend/docker-compose.yml`, `/docker-compose.yml` |
| Module 08 | unpinned `requirements.txt` | Not pinned | `08_recommendation_feedback/requirements.txt` |

LLM SDK, vector DB, embedding model: **Not found in code** (no `openai`, `groq`, `langchain`, `chromadb`, `sentence-transformers` imports anywhere).

## Folder tree (2–3 levels)

```text
/                                   repo root
├── docker-compose.yml              shared Keycloak only
├── identity/keycloak/              realm export imported by Keycloak
├── .github/workflows/              CI for 02 (lint, test, build+Trivy, openapi-diff, e2e)
└── DL-07-Agentic-AI-System-II/
    ├── 01_web_app/                 Next.js App Router UI
    │   ├── app/                    pages: /, /status, /admin, /api/health
    │   ├── components/             form, dashboard, map, context provider, ui/
    │   └── lib/                    api client, types, geocode, routing, mock data
    ├── 02_api_backend/             FastAPI gateway + Celery workers
    │   ├── app/api/                routers (/v1), deps, auth, idempotency, middleware
    │   ├── app/services/           use cases + ports.py (interfaces)
    │   ├── app/domain/             pure rules: normalization, safety gate, cache policy
    │   ├── app/infrastructure/     db (models, repos), redis stores, agent client, storage
    │   ├── app/workers/            Celery app, beat schedule, tasks
    │   ├── app/schemas/v1/         request/response contracts
    │   ├── migrations/versions/    Alembic 0001–0010
    │   ├── mock_agent/             fake Agent with 7 scenario JSON files
    │   ├── scripts/                seed, dev_token, export_openapi
    │   ├── tests/                  unit, api, contract, integration, e2e, support
    │   └── docs/                   requirements, API spec, data design, structure
    ├── 03_travel_ai_agent/         orchestrator: tools → evidence → 07
    │   └── travel_agent/tools/     allowlisted tools, live + mock implementations
    ├── 04_external_data_services/  provider adapters → canonical records
    ├── 05_data_integration/        records + routes → integrated context
    ├── 06_risk_knowledge_services/ risk scoring, knowledge retrieval, route analysis
    ├── 07_decision_llm_engine/     policy JSON, templates, explanation seam, audit JSONL
    └── 08_recommendation_feedback/ response formatting, feedback queue, live updates
```

## How to run

Backend stack (from `02_api_backend/`, see `02_api_backend/README.md` and `Makefile`):

```bash
uv sync
uv run pytest                     # integration tests need Docker (Testcontainers)
uv run pytest -m "not integration"
docker compose up -d --build --wait   # api, worker, beat, migrate, mock-agent, postgres, redis-core, redis-cache, minio
docker compose exec api python -m scripts.dev_token --sub alice --scope travel:read
uv run python -m scripts.export_openapi
```

Agent + decision engine (from `03_travel_ai_agent/`): `uv run uvicorn decision_engine.api:app --port 8050` and `uv run uvicorn travel_agent.api:app --port 8010`, or `docker compose up --build -d` (`03_travel_ai_agent/README.md`).

Web app (from `01_web_app/`): `docker compose up web` (dev) or `docker compose --profile prod up --build web-prod` (`01_web_app/docker-compose.yml`).

Shared identity (repo root): `docker compose up -d keycloak`.

Combined one-command stack for all modules: **Not found in code** (`/docker-compose.yml` header says it is "still open").

### Env var names (no values)

| Scope | Names | Source |
|---|---|---|
| 02 required | `DATABASE_URL`, `REDIS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`, `AGENT_SERVICE_URL`, `CORS_ALLOWED_ORIGINS` | `02_api_backend/README.md` "Configuration", `app/core/config.py` |
| 02 optional | `APP_ENV`, `LOG_LEVEL`, `LOG_JSON`, `REDIS_CACHE_URL`, `CELERY_BROKER_URL`, `JWKS_URL`, `DEV_JWT_SIGNING_KEY`, `AGENT_TOKEN_URL`, `AGENT_CLIENT_ID`, `AGENT_CLIENT_SECRET`, `AGENT_SERVICE_TOKEN`, `PSEUDONYM_SECRET`, `IP_HASH_SECRET`, `COLUMN_ENCRYPTION_KEYS`, `OBJECT_STORAGE_*`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OPS_ALLOWED_NETWORKS`, plus every tunable `P-xx` field (e.g. `RATE_LIMIT_USER`, `SYNC_AGENT_TIMEOUT_SECONDS`) | `02_api_backend/app/core/config.py:37-429` |
| 03 | `MAX_AGENT_STEPS`, `MAX_TOOL_CALLS`, `AGENT_TOTAL_TIMEOUT`, `TOOL_TIMEOUT_SECONDS`, `DECISION_SERVICE_URL`, `USE_MOCK_TOOLS`, `TOMTOM_API_KEY` | `03_travel_ai_agent/travel_agent/config.py`, `README.md` |
| 07 | `DECISION_POLICY_VERSION`, `PROMPT_VERSION`, `LLM_API_KEY`, `LLM_MODEL_EXPLAINER`, `TEMPERATURE`, `MAX_INPUT_TOKENS`, `MAX_OUTPUT_TOKENS`, `LLM_TIMEOUT`, `LLM_MAX_ATTEMPTS`, `SUPPORTED_LOCALES`, `ESCALATION_RULES`, `AUDIT_LOG_PATH` | `07_decision_llm_engine/decision_engine/config.py:10-25` |
| 08 | `RECOMMENDATION_SCHEMA_VERSION`, `FEEDBACK_RETENTION_DAYS`, `DATABASE_URL`, `REDIS_URL` | `08_recommendation_feedback/README.md` |
| 01 | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_DEFAULT_LOCALE`, `NEXT_PUBLIC_DEV_TOKEN`, `NEXT_PUBLIC_KEYCLOAK_URL`, `NEXT_PUBLIC_KEYCLOAK_REALM`, `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID`, `API_INTERNAL_URL` | `01_web_app/lib/api/client.ts:3`, `01_web_app/docker-compose.yml` |
| Keycloak | `KC_HOST_PORT`, `KC_ADMIN_USER`, `KC_ADMIN_PASSWORD`, `KC_DEV_USER_PASSWORD`, `KC_OPS_ADMIN_SECRET` | `/docker-compose.yml`, `/.env.example` |
