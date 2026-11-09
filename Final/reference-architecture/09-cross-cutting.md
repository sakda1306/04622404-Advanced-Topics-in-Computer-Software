# 09 — Cross-cutting concerns

> Paths are relative to `DL-07-Agentic-AI-System-II/`.

## Config and env

| Pattern | Detail | File |
|---|---|---|
| Grouped `BaseSettings` | 17 groups (`app`, `db`, `redis`, `auth`, `agent`, `limits`, `jobs`, `cache`, …) composed in one `Settings`; each reads `.env` | `02_api_backend/app/core/config.py:18`, `412-429` |
| Defaults with IDs | Every tunable has a default + spec id comment (`# P-30`) | `config.py:197-276` |
| Secrets typed `SecretStr` | DB/Redis URLs, keys, tokens | `config.py:71-81`, `120`, `161-162`, `305`, `392-395` |
| Fail fast before workers start | `app.serve` validates every group, prints all errors **without input values**, exits 2 | `02_api_backend/app/serve.py:33-67` |
| Prod guards | Dev JWT key refused outside dev/test; dev column-encryption key refused in prod | `02_api_backend/README.md` "Authentication", `config.py:146-150`, `404-410` |
| Policy-locking validators | Env cannot approve a policy, change escalation rules or pick an unknown prompt version | `07_decision_llm_engine/decision_engine/config.py:27-70` |
| Frontend | `NEXT_PUBLIC_*` baked at build time (build args) vs `API_INTERNAL_URL` runtime | `01_web_app/Dockerfile` builder stage, `01_web_app/docker-compose.yml` |

## Logging

| Pattern | File |
|---|---|
| structlog JSON, contextvars (`correlation_id`, `job_id`) bound per request/task | `02_api_backend/app/core/logging.py:50-82`, `app/workers/tasks/recommendation.py:21-25` |
| Redaction processor: keys matching `authorization`, `token`, `password`, `secret`, `cookie`, `api_key`, `email`, `lat`, `lon`, `question`, … ⇒ `[redacted]`; exceptions also redacted | `app/core/logging.py:15-60`, `logging.py:60-110` |
| Locations logged as geohash (precision 5 ≈ 5 km) | `config.py:333` |
| Event-name logging (`job_started`, `recommendation_cache_hit`, `safety_review_required`) | `app/services/agent_run_service.py:175`, `recommendation_service.py:263` |
| Never log validation input or provider error bodies | `app/api/error_handlers.py:29`, `app/infrastructure/agent/client.py:388`, `07_decision_llm_engine/decision_engine/explanation.py:110` |
| Access log off (uvicorn), app logs instead | `app/serve.py:80` |

## Rate limiting and quotas

| Limit | Default | Mechanism | File |
|---|---|---|---|
| Per IP | 120/min | Middleware before auth; keyed hash of IP | `app/api/middleware/rate_limit.py:20-45` |
| Per user | 60/min | Inside `authenticate` | `app/api/auth.py:61-77` |
| Per endpoint per user | 10/min (`recommend`) | `RateLimit("recommend", …)` dependency | `app/api/auth.py:112-134` |
| Algorithm | Sliding window on a Redis sorted set, one Lua script, Redis `TIME` as clock | `app/infrastructure/redis/rate_limiter.py:12-30` |
| Concurrency quota | 3 active jobs per user, 3 SSE streams per user | `app/infrastructure/redis/slots.py`, `config.py:203-204` |
| Daily quota | **Per-user daily LLM quota: Not found in code.** Closest pattern: once-per-24 h cooldown with `SET NX EX` returning remaining TTL as `Retry-After` | `app/infrastructure/redis/cooldown.py:15-20`, `app/services/export_service.py:76-84` |
| Redis down | Rate limit fails open (configurable) | `app/api/auth.py:42-46`, `config.py:213` |
| Agent budget | max steps 12, tool calls 20, per tool 5 s, total 60 s | `03_travel_ai_agent/travel_agent/config.py:23-29`, `travel_agent/budget.py` |

## Caching

| Cache | Key | TTL | Invalidation | File |
|---|---|---|---|---|
| Recommendation result | SHA-256 of `{origin/destination/waypoint geohash-6 cells, departure 15-min bucket, modes, avoid, mobility, max_hours, travelers, language}` | `min(300 s, valid_until - now)`; 0 ⇒ not cached | TTL only; never cache HIGH risk, stale or non-completed results, questions or conversations | `02_api_backend/app/domain/cache_policy.py:13-62` |
| Freshness re-check on read | Cached payload re-evaluated against staleness policy; stale ⇒ treated as miss | — | — | `app/services/recommendation_service.py:266-277`, `app/services/recommendation_payload.py` |
| Separate Redis for cache | 128 MB `allkeys-lru`, no persistence (losing it is harmless) | — | LRU | `02_api_backend/docker-compose.yml` `redis-cache` |
| Service status | aggregated from Agent reports | 30 s cache, 15 min window | TTL | `config.py:349-351` |
| Ready check of Agent | cached | 10 s | TTL | `config.py:349` |
| JWKS | cached | 600 s, min refresh 60 s | TTL / unknown `kid` refresh | `config.py:114-115` |
| External provider cache (04) | Not found in code (`CACHE_TTL` exists only in `/.env.example`) | — | — | — |

## Background tasks

Celery worker + beat with three queues (`recommendations`, `alerts`, `maintenance`); schedule in `app/workers/schedule.py:17-43`; one asyncio loop per worker process (`app/workers/runtime.py:175-220`); stuck-job reaper every 5 min; nightly purge. Module 08 uses an in-process `asyncio.create_task` loop instead (`08_recommendation_feedback/app/main.py:44-60`). Detail in `03-main-flows.md` §D.

## External API wrappers and fallbacks

| Wrapper | Timeout / retry | Fallback | File |
|---|---|---|---|
| Agent client (02→03) | deadline, 2 retries, exponential + jitter, honours `Retry-After`, circuit breaker in Redis | Job fails with stable error code; R-01 emergency fallback from DB by region+language | `02_api_backend/app/infrastructure/agent/client.py:175-265`, `circuit_breaker.py`, `app/services/agent_run_service.py:413-426` |
| Decision client (03→07) | Tenacity `AsyncRetrying`, `stop_after_attempt(2)`, `wait_exponential_jitter`, retry predicate | 503 `DECISION_UNAVAILABLE` | `03_travel_ai_agent/travel_agent/tools/decision.py:96-120` |
| Tool calls (03→04/05/06) | `asyncio.timeout(5 s)` each | Service marked `UNAVAILABLE`, run continues as partial | `03_travel_ai_agent/travel_agent/pipeline.py:208-241` |
| Open-Meteo / TomTom / GDACS | `urlopen(timeout=10)` etc. | Canonical `status: "unavailable"` record with `error_code` (`PROVIDER_UNAVAILABLE`, `PROVIDER_DATA_INVALID`) | `04_external_data_services/weather_service.py:32-80`, `tomtom_transport.py:99`, `gdacs_adapter.py:179` |
| Mock implementations behind the same interface | `MockToolSet` scenarios; `mock_agent` service with 7 scenarios switchable at runtime | — | `03_travel_ai_agent/travel_agent/tools/mocks.py:34-40`, `02_api_backend/mock_agent/main.py:93-109` |
| Fallback to cached data on provider failure | **Not found in code** | — | — |

## Security

| Area | Implementation | File |
|---|---|---|
| Secrets | `.env` git-ignored; `.env.example` with empty values; `SecretStr`; config errors omit values | `/.env.example`, `app/serve.py:53` |
| AuthN | OIDC JWT via JWKS (joserfc); Keycloak realm shared at repo root | `app/core/security.py`, `/identity/keycloak/` |
| AuthZ | Scopes per route; admin refusals audited | `app/api/auth.py:93-109`, `app/api/deps.py:174-177` |
| Agent service auth | OAuth client credentials or static token | `app/infrastructure/agent/auth.py`, `config.py:158-162` |
| Input validation | Strict Pydantic models (`extra="forbid"` via `_Strict`), length caps, domain normalisation limits | `app/schemas/v1/travel.py:27`, `app/domain/normalization.py` |
| Body limits | 64 KiB, JSON only | `app/api/middleware/body_guard.py` |
| File limits | Not found in code (no uploads) | — |
| Output sanitising | control chars stripped, safe URLs, internal keys removed | `app/domain/sanitizer.py:20-65` |
| PII | Pseudonymous user ids; keyed hashes for IPs/subjects in Redis; geohash in logs + ML records; AES-GCM column encryption for messages and feedback comments; admins see no places/questions/answers; consents recorded with server time | `app/core/crypto.py`, `app/core/encryption.py`, `models/mlops.py:50-55`, `02_api_backend/README.md` |
| Retention | Every user table has `expires_at`; nightly purge; account deletion job | `config.py:266-276`, `app/services/purge_service.py` |
| Headers | Security headers middleware, HSTS in prod, CORS allow-list without credentials | `app/main.py:81-108` |
| Ops endpoints | `/ready`, `/metrics` only from `OPS_ALLOWED_NETWORKS`, else 404 | `app/api/ops.py:41-50` |
| Containers | non-root users, apt upgrade at build, Trivy scan in CI | `02_api_backend/Dockerfile:15-17`, `/.github/workflows/api-backend-ci.yml:72` |
| Spans | query strings, client IPs, exception messages removed before export | `02_api_backend/README.md` "Health, metrics and tracing", `app/core/telemetry.py` |

## Testing

| Layer | Framework / approach | Location |
|---|---|---|
| Unit (pure) | pytest; domain + services with fakes; layering AST test | `02_api_backend/tests/unit/`, `tests/unit/domain/test_layering.py` |
| API | httpx `ASGITransport`, fake repos, `fakeredis` async, RSA signing key fixture for real JWT verification | `tests/api/fakes.py`, `tests/conftest.py:32-95` |
| Contract | AgentClient vs mock agent; `openapi.json` snapshot + structural check | `tests/contract/test_agent_contract.py`, `tests/contract/test_openapi_schema.py` |
| Integration | Testcontainers PostGIS + Redis; migrations drift test | `tests/integration/conftest.py`, `tests/integration/test_migrations.py` |
| E2E | Against running compose (`E2E_BASE_URL`); schemathesis fuzz on GETs (no 5xx) | `tests/e2e/`, `tests/e2e/test_openapi_contract_fuzz.py` |
| Test doubles | `FakeClock`, fake object store, Agent request builders | `tests/support/clock.py`, `tests/support/storage.py`, `tests/support/agent.py` |
| LLM mocks | No live LLM; tests use `ExplanationProvider` stubs | `07_decision_llm_engine/tests/test_explanation_audit.py` |
| Cross-module contract | 03 runs the **real** 07 in-process via `ASGITransport` (07 installed as editable dev dep) | `03_travel_ai_agent/tests/conftest.py:37-43`, `03_travel_ai_agent/pyproject.toml` |
| Fixtures as files | Scenario JSON for mock agent and 07 examples; `refresh_examples.py` rewrites timestamps | `02_api_backend/mock_agent/scenarios/`, `07_decision_llm_engine/examples/`, `scripts/refresh_examples.py` |
| Markers | `-m "not integration"` fast run; `-m e2e` | `02_api_backend/README.md` "Commands" |
| CI | ruff format/check, mypy, pytest + coverage, docker build + Trivy, oasdiff breaking-change check, compose e2e | `/.github/workflows/api-backend-ci.yml` |
| Frontend tests | Not found in code | — |
