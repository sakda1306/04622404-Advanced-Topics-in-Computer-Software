# 02 — API & Backend

FastAPI backend for the Real-Time Travel Safety & Advisory Assistant. It is the trust
boundary between the Web App and the Travel AI Agent.

Design documents:
[Requirements](docs/01_requirements.md) ·
[API Spec](docs/02_api_spec.md) ·
[Data Design](docs/03_data_design.md) ·
[Project Structure](docs/04_project_structure.md)

## Status

| Step | Scope | State |
|---|---|---|
| 5.1 | Skeleton: config, logging, errors, `/health`, Docker | done |
| 5.2 | DB models, Alembic 0001–0007, reference seed data | done |
| 5.3 | Auth (JWT/JWKS, scopes), rate limits, idempotency, body guard, security headers | done |
| 5.4 | Mock Agent (7 scenarios) and AgentClient: deadline, retry, circuit breaker, cancel, NDJSON | done |
| 5.5 | Domain: normalization, freshness (R-07), Safety Gate (R-01..R-05), sanitizer (R-06) | done |
| 5.6 | Recommendation flow: `POST/GET /v1/travel/recommendations`, Celery worker, job state and SSE in Redis, stream tickets, cache | done |
| 5.7 | Conversations and follow-up questions (`/v1/conversations`), recommendation history with cursor pagination | done |
| 5.8 | Trips, assessments and live alerts (`/v1/trips`, Celery beat), feedback and the safety review queue | done |
| 5.9a | Profile and consents (`/v1/me`), account deletion, job cancel (`DELETE /v1/jobs/{id}`), stuck-job reaper, anonymized prediction records | done |
| 5.9b | Data export on MinIO (`/v1/me/data-export`), nightly purge, monthly audit partitions, column encryption of messages and feedback comments | done |
| 5.10 | `/ready`, `/metrics` (API and worker), public `/v1/service-status`, OpenTelemetry tracing from HTTP through Celery to the Agent | done |
| 5.11 | Admin tools: job list, recommendation diagnostics, audit log, anonymized training data export (`/v1/admin/...`) | done |
| 5.12 | OpenAPI export (`openapi.json`), snapshot/structural/live-fuzz contract tests, GitHub Actions CI | done |

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`pip install uv`)
- Docker Desktop (for the compose stack)

## Quick start

```bash
uv sync
uv run pytest
```

Integration tests start a PostGIS container with Testcontainers, so Docker must be running.
Use `uv run pytest -m "not integration"` for a quick run without Docker.

Run the full stack (API, Celery worker and beat, mock Agent, PostGIS, Redis core, Redis cache, MinIO). The
`migrate` service applies migrations and seeds reference data before the API starts:

```bash
docker compose up -d --build --wait
curl http://localhost:8000/health
```

API docs: <http://localhost:8000/docs>

Run the API without Docker (needs a `.env`, see `.env.example`):

```bash
uv run python -m app.serve --reload
```

## Authentication in development

The dev stack signs tokens with `DEV_JWT_SIGNING_KEY` (HS256). Get a token and call the API:

```bash
docker compose exec api python -m scripts.dev_token --sub alice --scope travel:read
```

Outside dev/test the key is refused at startup and tokens are verified against the
issuer's JWKS (`JWKS_URL`, or discovery from `JWT_ISSUER`).

### With the team's Keycloak (D-01, D-101)

The shared Keycloak lives in the repo-root `docker-compose.yml` (see `identity/README.md`
at the repo root). To verify its tokens instead of dev tokens:

```bash
# repo root
docker compose up -d keycloak
# this folder
docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d --wait

TOKEN=$(curl -s -X POST http://localhost:8180/realms/travel-safety/protocol/openid-connect/token \
  -d grant_type=password -d client_id=dev-cli -d username=dev-user \
  -d password=dev-password-change-me | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/me
```

`docker-compose.keycloak.yml` empties `DEV_JWT_SIGNING_KEY` (while it is set the verifier
uses only the dev key) and points `JWKS_URL` at Keycloak through `host.docker.internal`,
because the token issuer is `localhost:8180`, which is not reachable from inside the
container. Admin scopes come only from the `ops-admin` client (client credentials).

## Recommendation flow

`POST /v1/travel/recommendations` stores the request, queues a Celery job and waits up to
`SYNC_AGENT_TIMEOUT_SECONDS` (8 s) for the result. The worker is the only component that
calls the Agent; it applies the Safety Gate before anything is stored or shown.

| `mode` | Result |
|---|---|
| `auto` (default) | `200` with the recommendation, or `202` + job when it takes longer |
| `sync` | `200`, or `504 AGENT_TIMEOUT` when it takes longer (the job keeps running) |
| `async` | always `202` + job |

Follow a job with `GET /v1/jobs/{id}` or Server-Sent Events on `GET /v1/jobs/{id}/events`.
Browsers using `EventSource` cannot send the `Authorization` header: get a single-use ticket
from `POST /v1/jobs/{id}/stream-ticket` and open `.../events?ticket=...`.

```bash
TOKEN=$(docker compose exec -T api python -m scripts.dev_token --sub alice \
  --scope travel:read --scope travel:write)
curl -s -X POST "http://localhost:8000/v1/travel/recommendations?mode=async" \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: demo-$(date +%s)" \
  -H "content-type: application/json" \
  -d '{"origin":{"lat":13.7563,"lon":100.5018},"destination":{"lat":18.7883,"lon":98.9853},
       "departure_time":"2026-09-20T01:00:00Z","timezone":"Asia/Bangkok"}'
curl -N -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/jobs/<job_id>/events
```

## Conversations

A conversation keeps the context for follow-up questions. The first message carries the
trip in `overrides`; later messages only send what changes, and the backend re-assesses
the last trip with those changes:

```bash
CONV=$(curl -s -X POST http://localhost:8000/v1/conversations \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: conv-$(date +%s)" \
  -H "content-type: application/json" -d '{"language":"th"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['conversation_id'])")
# First message: the whole trip
curl -s -X POST http://localhost:8000/v1/conversations/$CONV/messages \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: msg1-$(date +%s)" \
  -H "content-type: application/json" \
  -d '{"content":"ปลอดภัยไหม","overrides":{"origin":{"lat":13.7563,"lon":100.5018},
       "destination":{"lat":18.7883,"lon":98.9853},
       "departure_time":"2026-09-20T01:00:00Z","timezone":"Asia/Bangkok"}}'
# Follow-up: only what changes
curl -s -X POST http://localhost:8000/v1/conversations/$CONV/messages \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: msg2-$(date +%s)" \
  -H "content-type: application/json" \
  -d '{"content":"ถ้าออกช้ากว่าเดิม 3 ชั่วโมงล่ะ","overrides":{"departure_time":"2026-09-20T04:00:00Z"}}'
```

`GET /v1/conversations/{id}/messages` and `GET /v1/travel/recommendations` return pages
(`items`, `next_cursor`); pass `?cursor=` to get the next page.

## Trips and live alerts

Save a trip, assess it on demand, and turn on live alerts (the user must agree first;
the server records the consent time). Celery beat scans trips with alerts on every
`TRIP_ALERT_SCAN_MINUTES` and re-assesses those that leave within 24 hours; when the risk
changes, an assistant message appears in the trip's conversation.

```bash
TRIP=$(curl -s -X POST http://localhost:8000/v1/trips \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: trip-$(date +%s)" \
  -H "content-type: application/json" \
  -d '{"name":"เชียงใหม่ ก.ย.","origin":{"lat":13.7563,"lon":100.5018},
       "destination":{"lat":18.7883,"lon":98.9853},
       "departure_time":"2026-09-20T01:00:00Z","timezone":"Asia/Bangkok",
       "alerts":{"enabled":true,"consent_at":"2026-09-17T08:00:00Z"}}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['trip_id'])")
# Assess now; the answer is the same as for POST /v1/travel/recommendations
REC=$(curl -s -X POST http://localhost:8000/v1/trips/$TRIP/assessments \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: assess-$(date +%s)" \
  -H "content-type: application/json" -d '{"mode":"sync"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['recommendation_id'])")
# Change the time (JSON Merge Patch): last_assessment.outdated becomes true
curl -s -X PATCH http://localhost:8000/v1/trips/$TRIP \
  -H "Authorization: Bearer $TOKEN" -H "content-type: application/merge-patch+json" \
  -d '{"departure_time":"2026-09-20T04:00:00Z"}'
```

`GET /v1/trips/{id}/assessments` lists the assessments of a trip. Run a scan now instead
of waiting for beat:

```bash
docker compose exec worker celery -A app.workers.celery_app:celery_app call app.workers.tasks.trip_alerts.scan_trip_alerts --queue alerts
```

## Feedback and safety review

Users rate a finished recommendation or report a problem. `UNSAFE_ADVICE` and
`INCORRECT_INFO` reports wait in the safety review queue (log event
`safety_review_requested`, audit row `feedback.report`); reviewers need the
`safety:review` scope, and every review is audited.

```bash
curl -s -X POST http://localhost:8000/v1/recommendations/$REC/feedback \
  -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: fb-$(date +%s)" \
  -H "content-type: application/json" \
  -d '{"rating":1,"report_type":"UNSAFE_ADVICE","comment":"ถนนปิด"}'
REVIEWER=$(docker compose exec -T api python -m scripts.dev_token --sub reviewer \
  --scope safety:review)
curl -s -H "Authorization: Bearer $REVIEWER" http://localhost:8000/v1/admin/feedback/reviews
curl -s -X PATCH http://localhost:8000/v1/admin/feedback/reviews/<feedback_id> \
  -H "Authorization: Bearer $REVIEWER" -H "content-type: application/json" \
  -d '{"status":"approved","note":"ยืนยันแล้ว"}'
```

## Profile, consents and account deletion

`/v1/me` needs the `profile:read` / `profile:write` scopes. Consents are recorded with the
server time and audited; `analytics` allows anonymized prediction records, `live_alerts`
allows live trip alerts. Deleting the account answers `202`, stops running jobs and
removes the data in the background; until then the account gets `403`.

```bash
ME=$(docker compose exec -T api python -m scripts.dev_token --sub alice \
  --scope profile:read --scope profile:write)
curl -s -H "Authorization: Bearer $ME" http://localhost:8000/v1/me
curl -s -X PATCH http://localhost:8000/v1/me \
  -H "Authorization: Bearer $ME" -H "content-type: application/merge-patch+json" \
  -d '{"language":"en","consents":{"analytics":true}}'
curl -s -X DELETE -H "Authorization: Bearer $ME" http://localhost:8000/v1/me
```

Cancel a running job with `DELETE /v1/jobs/{id}` (`202`, or `409` when it has finished).
The worker stops the Agent run; the event stream ends with `cancelled`.

On Windows, `curl.exe` may replace Thai text in `-d '...'` with `?` before sending it.
Put the body in a UTF-8 file and send it with `--data-binary @body.json` instead.

## Data export, retention and encryption

`POST /v1/me/data-export` (scope `profile:read`, once a day) builds a zip of everything
stored about the user; `GET /v1/me/data-export/{id}` returns a download link valid for
15 minutes. Files are kept in MinIO (console: <http://localhost:9001>) for 7 days.

```bash
curl -s -X POST http://localhost:8000/v1/me/data-export \
  -H "Authorization: Bearer $ME" -H "Idempotency-Key: export-$(date +%s)"
curl -s -H "Authorization: Bearer $ME" http://localhost:8000/v1/me/data-export/<export_id>
```

A nightly job (03:00 Asia/Bangkok) deletes expired data and keeps monthly `audit_logs`
partitions. Message texts and feedback comments are encrypted in the database; set
`COLUMN_ENCRYPTION_KEYS` outside development (see `.env.example`).

## Admin tools

Admin routes need an admin scope and are written to the audit log, including refused
calls (a token without the scope gets `403` and a `denied` audit row). Admins see
diagnostics only: no user ids, places, questions or answers.

| Endpoint | Scope | What it returns |
|---|---|---|
| `GET /v1/admin/jobs?status=&type=&from=&to=` | `admin:read` | jobs in a time range (default: last 24 h, at most 31 days) |
| `GET /v1/admin/recommendations/{id}` | `admin:read` | status, safety rules applied, versions, Agent runs with trace ids |
| `GET /v1/admin/audit-logs?action=&result=&from=&to=` | `admin:read` | audit rows, newest first |
| `POST /v1/admin/exports/training-data` | `admin:write` | starts an export of anonymized prediction records and reviewer-approved feedback |
| `GET /v1/admin/exports/training-data/{id}` | `admin:write` | status and a 15-minute download link (gzip JSON Lines, kept 7 days) |

```bash
ADMIN=$(docker compose exec -T api python -m scripts.dev_token --sub admin-1 \n  --scope admin:read --scope admin:write)
curl -s -H "Authorization: Bearer $ADMIN" "http://localhost:8000/v1/admin/jobs?limit=5"
curl -s -X POST -H "Authorization: Bearer $ADMIN" -H "Idempotency-Key: train-$(date +%s)"   -H "content-type: application/json" -d '{}' http://localhost:8000/v1/admin/exports/training-data
```

## Health, metrics and tracing

| Endpoint | Who can call it | What it says |
|---|---|---|
| `GET /health` | anyone | the process is alive |
| `GET /ready` | internal networks only | `503` when PostgreSQL or redis-core is down; also reports redis-cache and the Agent |
| `GET /metrics` | internal networks only | Prometheus text for the API |
| `GET /v1/service-status` | anyone | `ok` / `degraded` / `unavailable` / `unknown` per service |

"Internal" means a client address inside `OPS_ALLOWED_NETWORKS` (private ranges by
default); requests from the internet get `404`. The worker serves its own metrics on
port 9101 inside the compose network:

```bash
curl -s http://localhost:8000/ready
docker compose exec worker python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9101/metrics').read().decode())"
```

The service status of weather, transport, disaster and the models comes from what the
Agent reported in recent answers (15 minutes). With no recent report a service shows
`unknown`, never `ok`.

To see traces, start Jaeger and point the backend at it, then open <http://localhost:16686>:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 docker compose --profile observability up -d --wait
```

Each request is one trace (API, Celery task, Agent call, SQL and Redis), tagged with
`app.correlation_id`; log lines inside it carry `trace_id`. Query strings, client
addresses and exception messages are removed before spans leave the process.

## Mock Travel AI Agent

Until Module 03 is ready, the `mock-agent` service (port 8010) implements the Agent
contract with canned scenarios from `mock_agent/scenarios/`:

| Scenario | What it returns |
|---|---|
| `low_risk` | fresh data, `TRAVEL_NORMALLY` |
| `high_risk` | flood warning, `AVOID_TRAVEL`, emergency instructions |
| `partial_disaster_down` | disaster service unavailable but still `TRAVEL_NORMALLY` (the safety gate must catch it) |
| `needs_clarification` | asks for the travel date |
| `bad_schema` | a body that breaks the contract |
| `slow_20s` | answers after 20 s (beyond the sync budget) |
| `unavailable_503` | 503 with `Retry-After: 2` |

Switch scenario at runtime:

```bash
curl -X PUT -H "content-type: application/json" -d '{"name":"high_risk"}' http://localhost:8010/_mock/scenario
```

To use the real Agent, set `AGENT_SERVICE_URL` and its credentials
(`AGENT_TOKEN_URL` + `AGENT_CLIENT_ID` + `AGENT_CLIENT_SECRET`, or `AGENT_SERVICE_TOKEN`).
`tests/contract/` holds the contract tests both teams can run.

## OpenAPI contract and CI

`openapi.json` at the repo root of this module is the contract for the Web App team.
Regenerate it after changing a route or schema:

```bash
make openapi   # or: uv run python -m scripts.export_openapi
```

`tests/contract/test_openapi_schema.py` fails the build if `openapi.json` drifts from
the running app, so `make openapi` and committing the result is part of the change, not
optional cleanup. It also pins that every `422` response documents the Problem Details
shape the API actually sends (`app/api/openapi.py`) — FastAPI's own default would show
its `HTTPValidationError` instead, which nothing in this app ever returns.
`tests/e2e/test_openapi_contract_fuzz.py` runs schemathesis against every `GET`
operation of the live compose stack; it only asserts "no 5xx", so it stays outside the
API-level tests' job of checking exact bodies.

`.github/workflows/api-backend-ci.yml` (at the repo root, scoped to this module with a
`paths:` filter) runs `lint`, `test`, `build` (+ Trivy), `openapi-diff` (breaking-change
check against the PR's base branch, via `oasdiff`) and `e2e` (PR into `develop` only).

## Commands

`make` targets are listed below. On Windows without `make`, run the command on the right.

| make | Command |
|---|---|
| `make install` | `uv sync` |
| `make up` | `docker compose up -d --build --wait` |
| `make down` | `docker compose down` |
| `make logs` | `docker compose logs -f api worker beat` |
| `make migrate` | `docker compose run --rm migrate` |
| `make downgrade` | `docker compose run --rm migrate alembic downgrade -1` |
| `make revision m="..."` | `uv run alembic revision -m "..."` |
| `make token` | `docker compose exec api python -m scripts.dev_token` |
| `make scenario s=high_risk` | switch the mock agent scenario (curl above) |
| `make seed` | `docker compose run --rm migrate python -m scripts.seed_reference_data` |
| `make test` | `uv run pytest` |
| `make test-e2e` | stack running, then `E2E_BASE_URL=http://localhost:8000 E2E_MOCK_AGENT_URL=http://localhost:8010 uv run pytest -m e2e tests/e2e` |
| `make test-fast` | `uv run pytest -m "not integration"` |
| `make test-integration` | `uv run pytest tests/integration` |
| `make cov` | `uv run pytest --cov --cov-report=term-missing` |
| `make lint` | `uv run ruff format --check .` and `uv run ruff check .` |
| `make format` | `uv run ruff format .` and `uv run ruff check --fix .` |
| `make typecheck` | `uv run mypy app tests migrations scripts` |
| `make openapi` | `uv run python -m scripts.export_openapi` (writes `openapi.json` for the Web App team) |
| `make check` | lint + typecheck + test |

## Configuration

All settings are read from environment variables by `app/core/config.py`.
Required: `DATABASE_URL`, `REDIS_URL`, `JWT_ISSUER`, `JWT_AUDIENCE`,
`AGENT_SERVICE_URL`, `CORS_ALLOWED_ORIGINS`. Tunable values (P-xx in the API spec)
have proposed defaults and can be overridden the same way.
The app refuses to start when a value is missing or invalid.

## Database migrations

- Every schema change goes through a new Alembic revision; never edit an applied one.
- Wrap CHECK constraint names in `op.f(...)`. Without it the naming convention adds the
  `ck_<table>_` prefix a second time.
- `tests/integration/test_migrations.py` fails when the models and migrations drift apart,
  including constraint and index names.

## Layout

```text
app/
  main.py              application factory
  serve.py             entrypoint: validates config, then starts uvicorn
  core/                config, logging, errors, ids, geo, encryption, metrics, telemetry
  api/                 routers (/v1), deps, auth dependencies, idempotency, middleware, error handlers,
                       openapi.py (fixes the 422 schema FastAPI infers by default)
  schemas/v1/          request and response contracts
  services/            use cases: recommendations, conversations, trips, alert scan, feedback,
                       jobs, users, worker run, payload (assess), me, exports, purge, ops
  domain/              enums, normalization, follow-up, trips, feedback, freshness, safety gate,
                       sanitizer, cache policy, profile, retention, service status
  infrastructure/db/   SQLAlchemy models, session, reference data, repositories
  infrastructure/audit.py audit log writer
  infrastructure/redis/ rate limiter, idempotency, job state, slots, tickets, cache, key names,
                       service status
  infrastructure/health.py dependency checks and Celery queue depth
  infrastructure/agent/ Agent contract, client, circuit breaker, service auth, factory
  workers/             Celery app, beat schedule, per-process runtime, signals, tasks
mock_agent/            Mock Travel AI Agent (dev and contract tests)
migrations/            Alembic revisions 0001-0009
scripts/               seed_reference_data, dev_token, export_openapi (writes openapi.json)
tests/
  unit/                pure tests, no I/O
  api/                 HTTP tests through httpx ASGITransport
  contract/            AgentClient against the mock agent, and the exported openapi.json
                       (snapshot + structural validation)
  integration/         PostGIS and Redis (Testcontainers), whole flow with the mock Agent
  e2e/                 against the running compose stack (skipped unless E2E_BASE_URL is set)
```
