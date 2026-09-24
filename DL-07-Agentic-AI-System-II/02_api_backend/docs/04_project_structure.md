# 04 — Project Structure: API & Backend

> สถานะ: **Draft v0.1** — เอกสารออกแบบเท่านั้น ยังไม่สร้างไฟล์โค้ดจริง (สร้างใน Phase 5)
> อ้างอิง: [02_api_spec.md](02_api_spec.md) · [03_data_design.md](03_data_design.md)
> การตัดสินใจของ Phase นี้อยู่ที่ [§12 Decision Log](#12-decision-log) (ต่อจาก D-17)

---

## 1. Directory Tree

```text
02_api_backend/
├── 01_env.txt / 02_step.txt / 03_process.txt   # แผนจากอาจารย์ (ไม่แก้)
├── docs/                                       # เอกสาร Phase 1–4
│
├── pyproject.toml              # dependencies + ruff/mypy/pytest config
├── uv.lock
├── Dockerfile                  # multi-stage: api / worker / beat ใช้ image เดียว
├── docker-compose.yml          # stack สำหรับ dev ของ backend เอง
├── .env.example                # ตัวแปรเฉพาะ backend (ค่าตัวอย่างเท่านั้น)
├── .dockerignore
├── Makefile                    # คำสั่งลัด (ดู §9)
├── alembic.ini
├── README.md
│
├── app/
│   ├── main.py                 # create_app(): FastAPI + middleware + routers + lifespan
│   ├── serve.py                # entrypoint: ตรวจ config แล้วเรียก uvicorn (D-25)
│   │
│   ├── core/                   # ── cross-cutting (ไม่มี business rule)
│   │   ├── config.py           # Settings (pydantic-settings) — P-xx ทั้งหมด
│   │   ├── logging.py          # structlog + PII redaction processor
│   │   ├── telemetry.py        # OpenTelemetry (FastAPI, httpx, SQLAlchemy, Celery, Redis) + ScrubbingExporter (5.10)
│   │   ├── metrics.py          # Prometheus metric objects, multiprocess mode (5.10)
│   │   ├── security.py         # JWT verify, JWKS cache, scopes
│   │   ├── errors.py           # AppError hierarchy + error codes
│   │   ├── ids.py              # UUIDv7, request/correlation id
│   │   ├── crypto.py           # HMAC pseudonym/ip hash
│   │   ├── encryption.py       # column encryption AES-GCM + key rotation (Step 5.9b)
│   │   ├── geo.py              # geohash, coordinate rounding
│   │   └── clock.py            # Clock abstraction (ทดสอบเวลาได้)
│   │
│   ├── api/                    # ── Presentation layer (HTTP / SSE — WS descoped, D-04)
│   │   ├── resources.py        # AppResources: verifier, redis, rate limiter, idempotency store
│   │   ├── auth.py             # get_principal, require_scopes, RateLimit (P-30, P-32)
│   │   ├── idempotency.py      # IdempotentRoute (spec §11.1)
│   │   ├── deps.py             # Depends: current user (JIT), services — ประกอบ infrastructure ที่นี่ที่เดียว
│   │   ├── audit.py            # ip hash + correlation id สำหรับ audit log (Step 5.8)
│   │   ├── middleware/
│   │   │   ├── request_context.py   # request_id, correlation_id, access log, last-resort 500
│   │   │   ├── body_guard.py        # 413 (P-44) / 415
│   │   │   ├── rate_limit.py        # per-IP limit (P-31)
│   │   │   ├── problem_asgi.py      # Problem Details จาก ASGI middleware
│   │   │   └── security_headers.py
│   │   ├── error_handlers.py   # AppError / ValidationError → Problem Details
│   │   ├── ops.py              # /health /ready /metrics (/ready, /metrics เฉพาะ network ภายใน — 5.10)
│   │   └── v1/
│   │       ├── router.py       # รวม router ทั้งหมดภายใต้ /v1
│   │       ├── recommendations.py
│   │       ├── jobs.py         # + SSE events + stream ticket
│   │       ├── ws.py
│   │       ├── conversations.py
│   │       ├── trips.py        # E-14..E-18 (Step 5.8)
│   │       ├── feedback.py     # E-19 (Step 5.8)
│   │       ├── me.py
│   │       ├── service_status.py  # E-23 (Step 5.10)
│   │       └── admin/
│   │           ├── access.py   # scope check + audit เมื่อถูกปฏิเสธ (Step 5.11)
│   │           ├── jobs.py     # GET /v1/admin/jobs (Step 5.11)
│   │           ├── recommendations.py  # diagnostics + agent runs (Step 5.11)
│   │           ├── reviews.py  # safety review queue (Step 5.8)
│   │           ├── exports.py  # training data export (Step 5.11)
│   │           └── audit.py    # GET /v1/admin/audit-logs (Step 5.11)
│   │
│   ├── schemas/                # ── API contract (Pydantic v2) — versioned
│   │   └── v1/
│   │       ├── common.py       # Location, Page, Problem, enums
│   │       ├── travel.py       # TravelRequest, RecommendationResponse, RouteOption, Hazard, ...
│   │       ├── jobs.py
│   │       ├── conversations.py
│   │       ├── trips.py
│   │       ├── feedback.py
│   │       ├── me.py
│   │       └── status.py
│   │
│   ├── services/               # ── Application layer (use cases)
│   │   ├── recommendation_service.py  # create (sync/async decision), get, list
│   │   ├── job_service.py             # status, cancel, events, tickets
│   │   ├── conversation_service.py    # conversations, messages, follow-up (Step 5.7)
│   │   ├── pagination.py              # cursor + Page (keyset)
│   │   ├── trip_service.py            # trips + การประเมิน (Step 5.8)
│   │   ├── trip_alert_service.py      # scan trip ที่เปิด live alert (Step 5.8)
│   │   ├── feedback_service.py        # + safety review routing, audit
│   │   ├── user_service.py            # JIT provisioning; ปฏิเสธบัญชีที่กำลังถูกลบ
│   │   ├── me_service.py              # profile, consent, ขอลบบัญชี (Step 5.9a)
│   │   ├── account_service.py         # ลบบัญชีจริง (task delete_account)
│   │   ├── reaper_service.py          # job ค้าง + ลบบัญชีที่ค้าง + export ค้าง (Step 5.9a/b)
│   │   ├── export_service.py          # data export (Step 5.9b)
│   │   ├── purge_service.py           # retention + partition audit (Step 5.9b)
│   │   ├── ops_service.py             # readiness + service status (Step 5.10)
│   │   ├── admin_service.py           # admin: jobs, recommendation, audit log (Step 5.11)
│   │   ├── training_export_service.py # training data export (Step 5.11)
│   │   ├── agent_run_service.py       # ใช้ใน worker: call agent → safety gate → persist
│   │   ├── recommendation_payload.py  # assess(): freshness → safety gate → payload ที่ sanitize แล้ว
│   │   ├── progress.py                # stage → % และข้อความตามภาษา
│   │   └── ports.py                   # Protocol + record ที่ services ใช้
│   │
│   ├── domain/                 # ── Domain layer (pure Python, ไม่ import FastAPI/SQLAlchemy)
│   │   ├── enums.py            # RiskLevel, RecommendationType, Status, Stage, ...
│   │   ├── errors.py           # DomainError, FieldIssue, InvalidInput
│   │   ├── normalization.py    # timezone, language, coordinates, preferences
│   │   ├── safety_gate.py      # R-01..R-07
│   │   ├── follow_up.py        # รวม overrides เข้ากับ request เดิม (Step 5.7)
│   │   ├── trips.py            # ตรวจ trip, merge patch, สถานะ, consent (Step 5.8)
│   │   ├── feedback.py         # ตรวจ feedback + review routing (Step 5.8)
│   │   ├── profile.py          # profile, consent, mask email (Step 5.9a)
│   │   ├── prediction.py       # prediction record แบบ anonymized (Step 5.9a)
│   │   ├── freshness.py        # is_stale / valid_until (P-28)
│   │   ├── sanitizer.py        # ตัด field ภายใน, ตรวจ URL, control chars
│   │   ├── cache_policy.py     # cache key + เงื่อนไขห้าม cache
│   │   ├── service_status.py   # สรุปสถานะ E-23 + กติกา readiness (Step 5.10)
│   │   └── retention.py        # คำนวณ expires_at, เดือนของ partition audit
│   │
│   ├── infrastructure/         # ── Repository & Client layer
│   │   ├── db/
│   │   │   ├── base.py         # DeclarativeBase + naming convention
│   │   │   ├── session.py      # async engine, session factory
│   │   │   ├── types.py        # EncryptedText (Step 5.9b) — Geography/JSON_DOC อยู่ใน base.py
│   │   │   ├── models/         # ORM: user.py, conversation.py (+messages), trip.py, request.py,
│   │   │   │                   #      recommendation.py, job.py (+agent_runs, data_exports),
│   │   │   │                   #      mlops.py (prediction_records, feedback, training_exports),
│   │   │   │                   #      audit.py, reference.py
│   │   │   ├── migration_filters.py  # autogenerate filter (ใช้ร่วมกับ drift test)
│   │   │   ├── reference_data.py     # seed coverage_areas / emergency_defaults
│   │   │   └── repositories/   # recommendations.py, conversations.py, requests.py, trips.py, feedback.py,
│   │   │                       #   users.py, exports.py, retention.py, admin.py, training_exports.py;
│   │   │                       #   ทุก read ของผู้ใช้รับ user_id (กัน IDOR)
│   │   ├── redis/
│   │   │   ├── clients.py      # core / cache connections
│   │   │   ├── keys.py         # key builders (ที่เดียวของ key format — data design §5)
│   │   │   ├── rate_limiter.py
│   │   │   ├── idempotency_store.py
│   │   │   ├── job_state.py    # HASH + STREAM + done signal
│   │   │   ├── slots.py        # จำกัดงานค้าง / stream ต่อ user (ZSET)
│   │   │   ├── tickets.py
│   │   │   ├── user_data.py    # ลบข้อมูล live ของ user (Step 5.9a)
│   │   │   ├── cooldown.py     # claim ที่หมดอายุเอง: export วันละครั้ง, purge ทีละรอบ (5.9b)
│   │   │   ├── service_status.py  # status:reports / status:service / ready:agent (5.10)
│   │   │   └── cache.py
│   │   ├── agent/
│   │   │   ├── client.py       # AgentClient (httpx): timeout, retry, deadline, cancel, NDJSON
│   │   │   ├── contracts.py    # Pydantic ของ Agent request/response (spec §9)
│   │   │   ├── circuit_breaker.py
│   │   │   ├── auth.py         # client credentials token
│   │   │   └── factory.py      # build_agent_client (ใช้ทั้ง api และ worker)
│   │   ├── queue.py            # CeleryJobQueue: ส่งงานจาก async code
│   │   ├── health.py           # ping DB / Redis, ความยาว queue ของ Celery (5.10)
│   │   ├── storage/
│   │   │   └── object_store.py # MinioObjectStore: put / delete / signed URL (Step 5.9b)
│   │   └── audit.py            # SqlAuditWriter (Step 5.8)
│   │
│   └── workers/                # ── Celery
│       ├── celery_app.py       # config, queues (สร้าง app ตอนใช้ครั้งแรก)
│       ├── runtime.py          # asyncio.Runner + resources ต่อ process (D-50)
│       ├── signals.py          # logging, tracing ต่อ process + /metrics ของ worker (5.10)
│       ├── tasks/
│       │   ├── recommendation.py   # run_recommendation(job_id)
│       │   ├── trip_alerts.py      # scan_trip_alerts: คิวประเมิน trip ใหม่ (Step 5.8)
│       │   ├── maintenance.py      # reap_stuck_jobs, delete_account, build_data_export,
│       │   │                       #   purge_expired (Step 5.9a/b)
│       └── schedule.py         # beat schedule (P-56; P-50 เพิ่มใน 5.9)
│
├── migrations/                 # Alembic
│   ├── env.py
│   └── versions/               # 0001_extensions ... 0007_reference_tables
│
├── mock_agent/                 # Mock Travel AI Agent (ใช้จนกว่า Module 03 พร้อม) — D-31
│   ├── main.py                 # POST /v1/agent/runs, DELETE /runs/{id}, /health, /_mock/scenario
│   └── scenarios/              # JSON: low_risk, high_risk, partial_disaster_down,
│                               #       needs_clarification, bad_schema, slow_20s, unavailable_503
│
├── scripts/
│   ├── seed_reference_data.py  # coverage_areas, emergency_defaults
│   ├── dev_token.py            # ออก JWT สำหรับ dev (local issuer)
│   └── export_openapi.py       # เขียน openapi.json ให้ทีม Web App
│
└── tests/
    ├── conftest.py
    ├── factories.py            # สร้าง test data
    ├── fixtures/               # agent responses (JSON)
    ├── unit/                   # domain + services (ไม่มี I/O)
    ├── integration/            # repositories, redis, alembic (Testcontainers)
    ├── api/                    # HTTP ผ่าน httpx.AsyncClient + respx mock agent
    ├── contract/               # OpenAPI snapshot, Agent contract
    └── e2e/                    # docker compose + mock_agent (optional ใน CI)
```

---

## 2. Layer Rules

```mermaid
flowchart LR
  subgraph Presentation
    API[api/ + schemas/]
    W[workers/]
  end
  S[services/]
  D[domain/]
  I[infrastructure/]
  C[core/]
  API --> S
  W --> S
  S --> D
  S --> I
  I --> D
  API -.-> C
  S -.-> C
  I -.-> C
  W -.-> C
```

| Layer | Import ได้ | ห้าม import |
|---|---|---|
| `domain` | stdlib, `core.clock`, `core.geo` | FastAPI, SQLAlchemy, Redis, httpx, Pydantic schemas ของ API |
| `services` | `domain`, `infrastructure` (ผ่าน interface/Protocol), `core` | `api`, `schemas` (รับ/คืน domain model) |
| `infrastructure` | `domain`, `core` | `api`, `services` |
| `api` | `services`, `schemas`, `core` | `infrastructure` โดยตรง (ยกเว้น `deps.py` ที่ประกอบ dependency) |
| `workers` | `services`, `core` | `api` |

- ตรวจอัตโนมัติด้วย **import-linter** ใน CI — *D-18*
- ข้อยกเว้น: `infrastructure` import `app.services.ports` และ `app.services.pagination` ได้ (record และ Protocol ที่ infrastructure implement) — *D-58*
- `services` พึ่ง **Protocol** (เช่น `RecommendationRepository`, `AgentPort`) → unit test ใส่ fake ได้โดยไม่ต้องมี DB
- การแปลง `schemas` ↔ `domain` ทำที่ `api` layer (mapper function ในไฟล์ router หรือ `schemas/v1/*`)

---

## 3. Request Flow → ไฟล์ที่เกี่ยวข้อง

| ขั้น (02_step.txt) | ไฟล์ |
|---|---|
| 1. รับ request | `api/v1/recommendations.py` |
| 2. auth / rate limit / schema | `core/security.py`, `api/middleware/rate_limit.py`, `schemas/v1/travel.py` |
| 3. request_id / correlation_id | `api/middleware/request_context.py` |
| 4. normalize | `domain/normalization.py` |
| 5–6. Agent / job queue | `services/recommendation_service.py` → `workers/tasks/recommendation.py` → `infrastructure/agent/client.py` |
| 7. progress | `infrastructure/redis/job_state.py` → `api/v1/jobs.py` (SSE) |
| 8. validate / sanitize | `infrastructure/agent/contracts.py`, `domain/safety_gate.py`, `domain/sanitizer.py` |
| 9. return + freshness | `domain/freshness.py`, `schemas/v1/travel.py` |
| 10. retention | `domain/retention.py`, `services/purge_service.py`, `infrastructure/db/repositories/retention.py` |
| 11. follow-up | `services/conversation_service.py` |
| error mapping | `core/errors.py`, `api/error_handlers.py` |

---

## 4. Configuration

### 4.1 Settings (`app/core/config.py`)

- ใช้ `pydantic-settings` อ่านจาก env → ไฟล์ `.env` (dev เท่านั้น)
- จัดกลุ่มเป็น nested settings: `app`, `db`, `redis`, `auth`, `agent`, `limits`, `retention`, `cache`, `observability`, `storage`, `secrets`
- ค่าทุกตัวใน spec §2 (P-xx) มี default = ค่าเสนอ → เปลี่ยนได้ด้วย env โดยไม่ต้องแก้โค้ด
- Secret ใช้ `SecretStr` (ไม่หลุดใน log/repr)
- Validate ตอน startup: ค่าผิด → process ไม่ start

### 4.2 Environment Variables

**บังคับ (จาก 01_env.txt — ตรงกับ `.env.example` ที่ root แล้ว)**

| Variable | ตัวอย่าง dev |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://tsa:tsa@postgres:5432/tsa` |
| `REDIS_URL` | `redis://redis-core:6379/0` (ใช้เป็น core) |
| `JWT_ISSUER` | `http://localhost:8000/dev-issuer` |
| `JWT_AUDIENCE` | `travel-safety-api` |
| `AGENT_SERVICE_URL` | `http://mock-agent:8010` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | ว่างได้ (ปิด tracing) |
| `LOG_LEVEL` | `INFO` |

**เพิ่มเติม (เสนอ — ต้องเพิ่มใน `.env.example` ตอน Phase 5)**

| Variable | หมายเหตุ |
|---|---|
| `APP_ENV` | `dev` / `test` / `staging` / `prod` — ใช้เป็น Redis key prefix |
| `REDIS_CACHE_URL` | ถ้าว่าง → ใช้ `REDIS_URL` DB `/1` (D-14) |
| `CELERY_BROKER_URL` | ถ้าว่าง → ใช้ `REDIS_URL` DB `/2` |
| `JWKS_URL` | ถ้าว่าง → ค้นจาก `{JWT_ISSUER}/.well-known/openid-configuration` |
| `DEV_JWT_SIGNING_KEY` | ใช้เฉพาะ `APP_ENV=dev/test` |
| `AGENT_CLIENT_ID`, `AGENT_CLIENT_SECRET` | service auth ไป Agent |
| `PSEUDONYM_SECRET`, `IP_HASH_SECRET`, `COLUMN_ENCRYPTION_KEY` | secret manager ใน prod |
| `OBJECT_STORE_URL`, `OBJECT_STORE_BUCKET`, `OBJECT_STORE_ACCESS_KEY`, `OBJECT_STORE_SECRET_KEY` | data export |
| `ENABLE_DOCS` | เปิด/ปิด `/docs` |
| `OTEL_SERVICE_NAME` | ชื่อ service ใน trace (`travel-safety-api` / `travel-safety-worker`) |
| `OPS_ALLOWED_NETWORKS` | CIDR ที่เรียก `/ready`, `/metrics` ได้ (D-90) |
| `PROMETHEUS_MULTIPROC_DIR`, `WORKER_METRICS_PORT` | metrics หลาย process และ port `/metrics` ของ worker (D-91) |
| P-xx config keys | ตาม spec §2 (ไม่ต้องใส่ถ้าใช้ค่า default) |

> ⚠️ `.env.example` ที่ root มี `FEEDBACK_RETENTION_DAYS=90` (Module 08) แต่ P-23 เสนอ 180 วัน → ต้องตกลงให้ตรงกัน (Open Q1)

### 4.3 Startup / Lifespan

1. โหลด Settings → ตั้ง logging + telemetry
2. สร้าง DB engine, Redis clients, AgentClient (httpx `AsyncClient` ตัวเดียว ใช้ connection pool)
3. Warm JWKS cache (ไม่ fail ถ้าไม่ได้ — `/ready` จะรายงาน)
4. Shutdown: ปิด httpx, Redis, DB engine ตามลำดับ

---

## 5. Docker

### 5.1 Dockerfile (multi-stage)

| Stage | ทำอะไร |
|---|---|
| `base` | `python:3.12-slim`, ติดตั้ง `libpq`/`libgeos` เท่าที่จำเป็น, user non-root `app` |
| `deps` | `uv sync --frozen --no-dev` |
| `dev` | + dev dependencies, mount source, `--reload` |
| `runtime` | copy venv + `app/` + `migrations/`, `HEALTHCHECK` เรียก `/health` |

- Image เดียวใช้ 3 บทบาทโดยเปลี่ยน command:
  - api: `python -m app.serve --workers 2` (ตรวจ config ก่อน แล้วค่อยเรียก uvicorn หลาย worker — D-25)
  - worker: `celery -A app.workers.celery_app:celery_app worker -Q recommendations,alerts,maintenance`
  - beat: `celery -A app.workers.celery_app:celery_app beat --schedule /tmp/celerybeat-schedule` (หนึ่งตัวต่อ stack, Step 5.8)
- Migration รันเป็น one-off service (`migrate`) ก่อน api start — ไม่รันใน api container

### 5.2 `docker-compose.yml` (backend dev stack)

| Service | Image | Port (host) | Depends on | หมายเหตุ |
|---|---|---|---|---|
| `api` | build `dev` | 8000 | migrate, redis-core, mock-agent | hot reload |
| `worker` | build `dev` | — | redis-core, postgres | |
| `beat` | build `dev` | — | redis-core | |
| `migrate` | build `dev` | — | postgres (healthy) | `alembic upgrade head` แล้วจบ |
| `postgres` | `postgis/postgis:16-3.4` | 5432 | — | volume `pgdata` |
| `redis-core` | `redis:7-alpine` | 6379 | — | `--appendonly yes --maxmemory-policy noeviction` |
| `redis-cache` | `redis:7-alpine` | 6380 | — | `--maxmemory 128mb --maxmemory-policy allkeys-lru` |
| `mock-agent` | build `mock_agent/` | 8010 | — | `MOCK_SCENARIO` env เลือก scenario |
| `minio` | `quay.io/minio/minio` | 9000/9001 | — | เปิดตลอด (data export, D-84); api/worker รอให้ healthy |
| `jaeger` | `jaegertracing/jaeger` (v2) | 16686 | — | profile `observability`; รับ OTLP เองจึงไม่มี collector แยก (D-89) |

- Network เดียว `backend`; ทุก service มี `healthcheck`
- Port ตรงกับ `.env.example` ที่ root (`api` 8000, agent 8010)
- ตอนรวมทีม: root `docker-compose.yml` ใช้ `include:` ไฟล์นี้ หรือ copy service `api`/`worker`/`beat` ไป แล้วเปลี่ยน `AGENT_SERVICE_URL` เป็น Agent ตัวจริง — *D-19*
- Prometheus/Grafana ใช้ของทีมกลาง (`08_monitoring`) → backend เปิด `/metrics` บน network ภายในเท่านั้น

---

## 6. Celery Layout

| Queue | Tasks | Concurrency (เสนอ) |
|---|---|---|
| `recommendations` | `run_recommendation` | 4 (prefork; งานส่วนใหญ่คือรอ Agent) |
| `alerts` | `scan_trip_alerts` (งานประเมินไปเข้า `recommendations`) | 2 — ตอนนี้ worker ตัวเดียวฟังทั้งสอง queue |
| `maintenance` | `reap_stuck_jobs`, `delete_account`, `build_data_export`, `build_training_export`, `purge_expired` | 1 — ตอนนี้ worker ตัวเดียวฟังทุก queue |

- `task_acks_late=True`, `worker_prefetch_multiplier=1`, `task_reject_on_worker_lost=True`
- Task รับแค่ `job_id` (ไม่ส่ง payload/PII ผ่าน broker) → โหลดจาก DB
- ส่ง `correlation_id` + `traceparent` ผ่าน task headers
- Task เป็น sync function เรียก `asyncio.run()` เข้า service async — *D-20*
- Retry เฉพาะ error ชั่วคราว (ตาม spec §9.5); ครบแล้ว → job `failed`

---

## 7. Dependencies (`pyproject.toml`)

| กลุ่ม | Packages |
|---|---|
| Core | `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `sse-starlette` |
| Data | `sqlalchemy>=2`, `alembic`, `asyncpg`, `geoalchemy2`, `shapely`, `python-geohash` (หรือ `pygeohash`), `redis>=5` |
| Auth / HTTP | `joserfc`, `httpx` |
| Jobs | `celery[redis]` |
| Observability | `structlog`, `prometheus-client`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-{fastapi,httpx,sqlalchemy,celery,redis}` |
| Utils | `uuid6` (UUIDv7), `tzdata`, `cryptography`, `orjson` |
| Dev / Test | `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `testcontainers[postgres,redis]`, `freezegun` หรือ Clock abstraction, `schemathesis`, `ruff`, `mypy`, `import-linter`, `pre-commit` |

- ใช้ **uv** จัดการ dependency + lock (`uv.lock` มีใน `.gitattributes` แล้ว) — *D-21*
- ใช้ **joserfc** ตรวจ JWT (ไม่ติดตั้ง python-jose หรือ `authlib.jose` คู่กัน) — *D-22*
- Celery อย่างเดียว ไม่มี RQ/Arq (ตาม 01_env.txt)

---

## 8. Testing Strategy

| ระดับ | ทดสอบอะไร | เครื่องมือ | รันใน CI |
|---|---|---|---|
| Unit | domain (safety gate, normalization, freshness, cache policy), services กับ fake repo | pytest | ทุก push |
| Integration | repositories + PostGIS, Redis keys/TTL, Alembic upgrade/downgrade | Testcontainers | ทุก push |
| API | ทุก endpoint: auth, IDOR, rate limit, idempotency, error shape, SSE | httpx `AsyncClient`, respx | ทุก push |
| Contract | OpenAPI snapshot ไม่เปลี่ยนโดยไม่ตั้งใจ; Agent fixtures ผ่าน `contracts.py`; fuzz schema | schemathesis | ทุก push |
| E2E | compose stack + mock-agent ทุก scenario | pytest + docker compose | PR เข้า develop |

**Test cases บังคับ (Safety):**
- R-01..R-07 ทุกข้อมี test ทั้งกรณีผ่าน/ไม่ผ่าน
- disaster ล่ม → ไม่มีวันได้ `TRAVEL_NORMALLY`
- user A เข้าถึง resource ของ user B → 404
- log ไม่มี token / email / พิกัดละเอียด (capture log แล้ว assert)

**Coverage เป้าหมาย (เสนอ):** รวม ≥ 80%, `domain/` ≥ 95%

---

## 9. Developer Commands (Makefile)

| คำสั่ง | ทำอะไร |
|---|---|
| `make up` / `make down` | เปิด/ปิด compose stack |
| `make logs` | ดู log api + worker |
| `make migrate` / `make revision m="..."` | Alembic |
| `make seed` | reference data |
| `make token` | ออก dev JWT |
| `make test` / `make test-unit` / `make test-e2e` | pytest |
| `make lint` | ruff + mypy + import-linter |
| `make openapi` | เขียน `openapi.json` |
| `make scenario s=high_risk` | เปลี่ยน scenario ของ mock-agent |

> บน Windows ใช้ผ่าน Git Bash หรือ WSL; ถ้าไม่มี `make` ใช้คำสั่งเต็มใน README

---

## 10. Code Conventions

| หัวข้อ | กติกา |
|---|---|
| Style | ruff (format + lint), line length 100 |
| Typing | mypy strict ใน `domain/`, `services/`; ที่เหลือ standard |
| Async | I/O ทั้งหมดเป็น async ใน api; ห้าม blocking call ใน event loop |
| Naming | ไฟล์ `snake_case`, class `PascalCase`, Pydantic schema ลงท้าย `Request`/`Response`, ORM ลงท้าย `Model` |
| Errors | raise `AppError(code=...)` เท่านั้น ห้าม `HTTPException` ใน services/domain |
| Logging | `log.info("event_name", key=value)` — ชื่อ event เป็น snake_case, ห้าม f-string ใส่ข้อมูลผู้ใช้ |
| Comments | ภาษาอังกฤษ สั้น อธิบาย "ทำไม" ไม่ใช่ "ทำอะไร" |
| Commits | Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`) |
| Branch | `sakda-02-api-backend` → PR เข้า `develop` |

---

## 11. CI Pipeline (GitHub Actions — เสนอ)

1. `lint` — ruff, mypy, import-linter
2. `test` — unit + integration + api + contract (Testcontainers ใช้ Docker ของ runner)
3. `build` — build image `runtime`, scan ด้วย Trivy
4. `openapi-diff` — เทียบ `openapi.json` กับ `develop` แจ้งถ้ามี breaking change
5. `e2e` — เฉพาะ PR เข้า `develop`

> ใช้ `paths:` filter ให้ทำงานเมื่อไฟล์ใน `DL-07-Agentic-AI-System-II/02_api_backend/**` เปลี่ยนเท่านั้น (repo รวม 8 โมดูล)

---

## 12. Decision Log

| ID | การตัดสินใจ (ปัจจุบัน) | ทางเลือกอื่น | สถานะ |
|---|---|---|---|
| D-18 | บังคับ layer rule ด้วย import-linter | review ด้วยคน | Proposed |
| D-19 | Backend มี compose ของตัวเอง + ให้ root compose `include:` | root compose ไฟล์เดียว | Proposed (คุยทีม) |
| D-20 | Celery task sync + `asyncio.run()` | Celery + async pool เฉพาะ / เปลี่ยนเป็น Arq | Proposed |
| D-21 | uv จัดการ dependency | pip + requirements.txt / poetry | Proposed |
| D-22 | ~~Authlib~~ → **joserfc** (ไลบรารี JOSE ตัวใหม่จากผู้พัฒนา Authlib; `authlib.jose` ถูก deprecate) | python-jose | Accepted (Step 5.3) |
| D-23 | ~~SSE ใช้ `sse-starlette`~~ → แทนด้วย D-37 | เขียน `StreamingResponse` เอง | Superseded (Step 5.6) |
| D-24 | Mock Agent อยู่ใน repo ของ backend | ให้ Module 03 ทำ stub | Accepted (Step 5.4) |
| D-31 | Mock Agent ใช้ image `tsa-backend:dev` เดียวกัน (ไม่มี Dockerfile แยก) และไม่ import โค้ด backend | image แยก | Accepted (Step 5.4) |
| D-32 | Circuit breaker เก็บ state ใน Redis ใช้เวลาจาก app clock (ทดสอบได้) | Redis `TIME` / in-process | Accepted (Step 5.4) |
| D-33 | Service auth ไป Agent: client credentials (prod) หรือ static token (dev); ไม่ตั้งเลย = ไม่ส่ง header | mTLS | Accepted (Step 5.4) |
| D-28 | Rate limit **fail open** เมื่อ Redis ล่ม (ตั้งค่าได้), Idempotency **fail closed** (503) | ทั้งคู่ fail closed | Accepted (Step 5.3) |
| D-29 | Idempotency เก็บเฉพาะ response 2xx | เก็บทุก response ยกเว้น 5xx (แบบ Stripe) | Accepted (Step 5.3) |
| D-30 | Dev token ใช้ HS256 จาก `DEV_JWT_SIGNING_KEY`; production ใช้ JWKS (RS/ES/PS/EdDSA เท่านั้น) | dev issuer ที่มี JWKS endpoint | Accepted (Step 5.3) |
| D-34 | R-02 เปลี่ยนเฉพาะ `TRAVEL_NORMALLY` เป็น `null`; action ที่ระวังกว่าคงไว้ + `partial_result`; `not_used` ของ weather/disaster นับว่าไม่มีข้อมูล | null ทุก action | Accepted (Step 5.5) |
| D-35 | Agent ตอบ `failed` → 503 (ไม่ใช่ 502) เพราะ Agent ยังตอบตามสัญญา | 502 | Accepted (Step 5.5) |
| D-36 | ตรวจ timezone กับ `available_timezones()` + แพ็กเกจ `tzdata` (Windows ตัด space/จุดท้ายชื่อไฟล์ ทำให้การเปิดไฟล์อย่างเดียวผ่านผิด) | `ZoneInfo(name)` อย่างเดียว | Accepted (Step 5.5) |
| D-37 | SSE เขียนเองด้วย `StreamingResponse` (Starlette 1.6 ยกเลิก generator เมื่อ client หลุด); heartbeat ของเราเองต่ออายุ stream slot | `sse-starlette` | Accepted (Step 5.6) |
| D-38 | API ที่รอแบบ sync อ่าน event stream ของ job (`XREAD BLOCK` ≤ 1 s ต่อครั้ง); ไม่มี key `job:{id}:done` | `BLPOP` บน key แยก | Accepted (Step 5.6) |
| D-39 | `jobs:active` / `streams` เป็น ZSET (score = เวลาหมดอายุ) ปรับด้วย Lua ตัวเดียว | SET + TTL ทั้ง key | Accepted (Step 5.6) |
| D-40 | Stream ticket เก็บใต้ `sha256(ticket)` และใช้ `GETDEL` | ticket ดิบใน key | Accepted (Step 5.6) |
| D-41 | ทุก recommendation อยู่ใน conversation (สร้างให้ถ้าไม่ส่งมา); คำถามเก็บเป็น message `user`, summary เป็น `assistant` | สร้าง conversation เฉพาะเมื่อ follow-up | Accepted (Step 5.6) |
| D-42 | `agent_runs` หนึ่งแถวต่อการเรียก `AgentClient.run()` (`id` = `run_id`); retry ภายในบันทึกแค่ใน log | หนึ่งแถวต่อ HTTP attempt | Accepted (Step 5.6) |
| D-43 | JIT user provisioning แบบย่อ (แถว `users` ต่อ `iss`+`sub`) ทำใน 5.6; profile/consent/ลบบัญชีอยู่ 5.9 | รอ 5.9 | Accepted (Step 5.6) |
| D-44 | `mode=sync` ที่เกิน P-02 → `504 AGENT_TIMEOUT` (job ทำต่อ) | รอถึง P-04 | Accepted (Step 5.6) |
| D-45 | อ่าน cache เฉพาะ `auto`/`sync`; ข้อมูลใน cache ที่ stale แล้ว = miss | ใช้ cache ทุก mode | Accepted (Step 5.6) |
| D-46 | ไม่มี retry ระดับ Celery task (AgentClient retry ตาม P-07 แล้ว) | Celery autoretry | Accepted (Step 5.6) |
| D-47 | `service_status` ที่ส่งให้ผู้ใช้มีเฉพาะ service ที่รู้จัก; Safety Gate ยังนับทุก service | ส่งทุก key | Accepted (Step 5.6) |
| D-48 | R-02 ตัด `TRAVEL_NORMALLY` แล้วตัด `reasons` และ `suggested_departure_time` ของ Agent ด้วย | เก็บไว้ | Accepted (Step 5.6) |
| D-49 | ข้อความ progress สร้างโดย backend ตามภาษา; ไม่แสดงข้อความจาก Agent | ส่งต่อข้อความ Agent | Accepted (Step 5.6) |
| D-50 | Celery task ใช้ `asyncio.Runner` หนึ่งตัวต่อ process และส่ง `contextvars.copy_context()` ทุกครั้ง (ขยาย D-20) | `asyncio.run()` ต่อ task | Accepted (Step 5.6) |
| D-51 | ใช้ `redis` 6.4 ตามที่ `kombu[redis]` รองรับ (`<6.5`) | redis 8 + celery ไม่มี extra | Accepted (Step 5.6) |
| D-52 | `POST .../messages` ที่ `stream=true` ตอบ `202` เสมอ; `false` = `mode=auto` | ให้ client เลือก mode เอง | Accepted (Step 5.7) |
| D-53 | follow-up เป็น job ชนิด `MESSAGE` (`source = MESSAGE`) ผ่าน worker เดิม | worker แยก | Accepted (Step 5.7) |
| D-54 | `overrides` แทนทั้ง field ยกเว้น `preferences` (รวมทีละ key); conversation ว่างต้องส่ง trip ครบ | JSON Merge Patch เต็มรูปแบบ | Accepted (Step 5.7) |
| D-55 | `200` ของ follow-up คือ `Message` ของ assistant; job ที่จบบันทึกข้อความเสมอ (มีข้อความสำรองเมื่อไม่มีคำแนะนำ) | ตอบ `RecommendationResponse` | Accepted (Step 5.7) |
| D-56 | cursor / `limit` ผิด → `422 VALIDATION_ERROR` พร้อมชื่อ field | `400 INVALID_REQUEST` | Accepted (Step 5.7) |
| D-57 | list conversations เรียงตาม `updated_at` (index เดิม); รายการที่เปลี่ยนระหว่างเปิดหน้าอาจย้ายที่ | เรียงตาม `created_at` | Accepted (Step 5.7) |
| D-58 | `infrastructure` import `services.ports` / `services.pagination` ได้ (Protocol + record ของ port) | ย้าย port ไป `domain` | Accepted (Step 5.7) |
| D-59 | trip บันทึกล่วงหน้าได้ถึง P-55; P-43 ใช้ตอนประเมิน; ตรวจช่วงเวลาเฉพาะเมื่อ `departure_time` เปลี่ยน | ใช้ P-43 ทุกที่ | Accepted (Step 5.8) |
| D-60 | `PATCH /v1/trips/{id}` เป็น JSON Merge Patch; location แทนทั้งก้อน, `preferences`/`alerts` รวมทีละ key; `null` บน field บังคับ → 422 | PUT ทั้งก้อน | Accepted (Step 5.8) |
| D-61 | สถานะ trip `PLANNED → ACTIVE/COMPLETED/CANCELLED`, `ACTIVE → COMPLETED/CANCELLED`; trip ที่ปิดแล้วแก้หรือประเมินไม่ได้ | เปลี่ยนสถานะได้อิสระ | Accepted (Step 5.8) |
| D-62 | เปิด alert ต้องส่ง `consent_at`; เก็บเวลาของ server; ปิด alert ล้าง consent | เก็บเวลาที่ client ส่ง | Accepted (Step 5.8) |
| D-63 | ประเมิน trip ใช้ conversation เดิมของ trip; `jobs.type = TRIP_ASSESSMENT` สำหรับ source `TRIP_ASSESSMENT` และ `TRIP_ALERT` | conversation ใหม่ทุกครั้ง | Accepted (Step 5.8) |
| D-64 | `last_assessment` = ผลล่าสุดที่จบแล้ว; ล้าง `outdated` เมื่อ request ตรงกับ trip ปัจจุบันเท่านั้น; job ที่ fail ไม่เปลี่ยนอะไร | ล้างทุกครั้งที่มีผล | Accepted (Step 5.8) |
| D-65 | beat สั่ง `scan_trip_alerts` ทุก P-56 (queue `alerts`) → คิวประเมินแบบ async ตาม P-57/P-58/P-59; ข้าม user ที่ชน P-33; container `beat` ย้ายมาทำใน 5.8 | task แยกต่อ trip / ตั้ง ETA ต่อ trip | Accepted (Step 5.8) |
| D-66 | alert แบบ in-app = ข้อความ assistant ใน conversation ของ trip เฉพาะเมื่อ risk level หรือ type เปลี่ยน; อ่านด้วย polling `GET /v1/conversations/{id}/messages` (WS descoped, D-04) | ตาราง notifications | Accepted (Step 5.8, อัปเดตช่องทางอ่าน 2026-09-19) |
| D-67 | รับ feedback เฉพาะ recommendation ที่จบแล้วและมีเนื้อหา; ส่งได้หลายครั้ง | หนึ่งครั้งต่อ recommendation | Accepted (Step 5.8) |
| D-68 | "แจ้ง Ops" = log warning `safety_review_requested` + audit `feedback.report` + metric `safety_review_requested_total` (5.10); alert rule เป็นของ `08_monitoring` | ส่ง email / webhook | Accepted (Step 5.8) |
| D-69 | review queue (`safety:review`) ทำใน 5.8; ค่า status เป็นตัวพิมพ์เล็ก; review ได้เฉพาะ `pending` (`409 REVIEW_NOT_PENDING`); approved → `usable_for_training` | รอ 5.11 | Accepted (Step 5.8) |
| D-70 | `SqlAuditWriter` เขียนลง default partition; `actor_ref` = pseudonym (user) หรือ `sub` (staff); `ip_hash` = HMAC | เขียน audit ผ่าน log | Accepted (Step 5.8) |
| D-71 | migration `0008`: index `recommendations (trip_id, created_at DESC) WHERE trip_id IS NOT NULL` | ไม่มี index | Accepted (Step 5.8) |
| D-72 | E-05 ยกเลิกใน DB ทันที + event `cancelled` + คืน slot; ไม่ใช้ Celery revoke; worker ตรวจ DB ทุก 1 วินาทีระหว่างรอ Agent แล้วยกเลิก run ที่ Agent | Celery revoke | Accepted (Step 5.9a) |
| D-73 | ผล/ความล้มเหลวที่มาหลัง job ไม่ active แล้วถูกทิ้ง; Redis job hash ไม่ย้อนจาก terminal (Lua) | เขียนทับตามลำดับที่มาถึง | Accepted (Step 5.9a) |
| D-74 | reaper (beat ทุก P-60, queue `maintenance`) ปิด job ที่เก่ากว่า P-04 × 2 เป็น `failed` + `AGENT_TIMEOUT` | ปล่อยให้ค้าง | Accepted (Step 5.9a) |
| D-75 | worker เขียน `prediction_records` ของผลสำเร็จเมื่อ user มี consent analytics; สร้างด้วยฟังก์ชัน domain (geohash P-48) | เขียนทุก user | Accepted (Step 5.9a) |
| D-76 | `PATCH /v1/me` เป็น merge patch; ตรวจ language/timezone/region; consent on/off บันทึกเวลา server + audit `user.consent` | PUT ทั้งก้อน | Accepted (Step 5.9a) |
| D-77 | consent `live_alerts` ของ user เป็นสวิตช์หลักของ alert ทุก trip | consent แยกต่อ trip อย่างเดียว | Accepted (Step 5.9a) |
| D-78 | `DELETE /v1/me` ทำสองจังหวะ: API mark + หยุด job + ลบ Redis + audit + queue; ระหว่างรอ → 403; reaper ส่งใหม่หลัง P-61 | ลบทันทีใน request | Accepted (Step 5.9a) |
| D-79 | `delete_account`: anonymize feedback แล้ว `DELETE users` (cascade); audit `user.delete` actor `system`; รันซ้ำได้ | soft delete | Accepted (Step 5.9a) |
| D-80 | `/v1/me` ใช้ scope `profile:*`; `email_masked` มาจาก token ไม่เก็บ | เก็บ email | Accepted (Step 5.9a) |
| D-81 | column encryption AES-256-GCM ใน application (`enc:v1:<kid>:...`, AAD = ชื่อ column); `COLUMN_ENCRYPTION_KEYS` key แรก active; dev มี key ในตัวแต่ prod ต้องตั้ง; ความยาวตรวจใน app; migration `0009` เข้ารหัสแถวเดิม | pgcrypto ใน DB / disk encryption อย่างเดียว | Accepted (Step 5.9b) |
| D-82 | data export ไม่มีแถว `jobs` — `data_exports.status` คือสถานะ; zip ของ JSON ที่ `exports/{export_id}.zip`; หมดอายุ P-49 แล้ว purge ลบไฟล์; export ค้างเกิน 30 นาที reaper ตั้ง `failed` | สร้าง job `DATA_EXPORT` + SSE | Accepted (Step 5.9b) |
| D-83 | ขอ export ได้หนึ่งครั้งต่อ P-63 (Redis claim `lock:export:{user_id}`) → `429` + `Retry-After`; ถ้าส่งเข้า queue ไม่ได้ คืน claim | rate limiter ทั่วไป | Accepted (Step 5.9b) |
| D-84 | MinIO ใน compose (image `quay.io/minio/minio` เพราะ Docker Hub เลิกให้ดึง); ลิงก์ดาวน์โหลดเซ็นด้วย client ของ public URL; ไม่ตั้ง storage → `503`; ลบบัญชีแล้วลบไฟล์ export | เก็บไฟล์ใน Postgres | Accepted (Step 5.9b) |
| D-85 | purge: beat cron P-50 ในเขตเวลา `PURGE_TIMEZONE` (timezone ของ Celery app); Redis claim `lock:purge`; ลบทีละ 1000; partition audit เดือนนี้ + 2 เดือนล่วงหน้า; drop partition เก่ากว่า P-24; audit `retention.purge` เก็บแค่จำนวน | pg_partman / cron ของ DB | Accepted (Step 5.9b) |
| D-86 | `/v1/me/data-export` ใช้ scope `profile:read` และต้องมี `Idempotency-Key` | `profile:write` | Accepted (Step 5.9b) |
| D-87 | `/ready` = 503 เฉพาะเมื่อ PostgreSQL หรือ redis-core ใช้ไม่ได้; `redis_cache` และ `agent` รายงานอย่างเดียว (ทุก replica ใช้ร่วมกัน ถอดทุก pod ไม่ช่วย); timeout 2 s ต่อ check; ไม่มี host / ข้อความ error ใน body | ให้ Agent ล่มแล้ว not ready | Accepted (Step 5.10) |
| D-88 | E-23 ใช้สถานะที่ Agent รายงานในคำตอบล่าสุด (worker เขียน `status:reports`) + circuit breaker + Agent `/health`; ไม่มีรายงานภายใน P-64 → `unknown`; status รวมมีค่า `unknown` เพิ่ม; cache P-65 | backend เรียก provider เอง (ขัด D-03) / ขอ endpoint ใหม่จาก Agent | Accepted (Step 5.10) |
| D-89 | Tracing: OTLP/HTTP (ไม่ใช้ gRPC เพื่อไม่ต้องลง grpcio); instrument FastAPI, httpx, SQLAlchemy, Celery, Redis; `ScrubbingExporter` ตัด query string, IP ของ client, ข้อความ exception และ status description ก่อนส่งออก; dev ใช้ Jaeger v2 รับ OTLP ตรง (profile `observability`) | OTel Collector ใน dev | Accepted (Step 5.10) |
| D-90 | `/ready` และ `/metrics` ตอบเฉพาะ IP ใน `OPS_ALLOWED_NETWORKS` (default loopback + private) อื่น ๆ `404`; IP มาจาก uvicorn หลัง resolve proxy ที่เชื่อถือ | bearer token สำหรับ scrape | Accepted (Step 5.10) |
| D-92 | Training export: ตาราง `training_exports` (ไม่ผูกผู้ใช้); งาน `build_training_export` บน queue `maintenance` เขียน gzip JSON Lines ลงไฟล์ชั่วคราวแล้ว upload (`fput_object`) ไม่ถือไว้ใน memory; ข้อมูล = `prediction_records` + feedback ที่ `usable_for_training` เท่านั้น (ไม่มี comment, `recommendation_id`, `pseudonymous_id`); ไฟล์อายุ P-68; purge / reaper ดูแลเหมือน data export; GET ใช้ scope `admin:write` เหมือน POST | ตอบไฟล์แบบ sync / ใช้ `data_exports` ร่วม | Accepted (Step 5.11) |
| D-93 | query ของ admin ต้องอยู่ในช่วงเวลา (default 24 ชม., สูงสุด P-67) และใช้ keyset cursor; index ใหม่ `jobs (created_at DESC, id DESC)` (migration `0010`) | ไม่จำกัดช่วง | Accepted (Step 5.11) |
| D-94 | admin เห็นแค่ diagnostics: ไม่มี `user_id`, ชื่อสถานที่, พิกัด, คำถาม, payload; audit log ไม่แสดง `ip_hash` | แสดง `user_id` เพื่อ support | Accepted (Step 5.11) |
| D-95 | ทุก admin endpoint (รวม review queue) ใช้ `admin_actor(scope, action)`: token ถูกแต่ขาด scope → `403` + audit `denied` (`required_scope`); ไม่มี DB → ยังตอบ `403` แต่ไม่บันทึก; ไม่มี token → `401` ไม่บันทึก | บันทึกเฉพาะที่ผ่านสิทธิ์ | Accepted (Step 5.11) |
| D-91 | Prometheus multiprocess mode เมื่อตั้ง `PROMETHEUS_MULTIPROC_DIR` (runtime image ตั้งไว้แล้ว); `app.serve` และ worker main process ล้าง directory ตอนเริ่ม; worker เปิด `/metrics` ของตัวเองที่ `WORKER_METRICS_PORT`; metric ที่อ่านตอน scrape (`celery_queue_depth`) ใช้ collector ชั่วคราว; `route` label เป็น template | push gateway | Accepted (Step 5.10) |
| D-26 | Enum เก็บเป็น `VARCHAR` + CHECK (ไม่ใช้ PostgreSQL ENUM) เพื่อเพิ่มค่าได้ใน migration ง่าย | PostgreSQL ENUM | Accepted (Step 5.2) |
| D-27 | Role DB (`tsa_migrator`, `tsa_app`, `tsa_purge`, `tsa_readonly`) สร้างตอน deploy ไม่ใช่ใน migration | สร้างใน migration | Accepted (Step 5.2) |
| D-25 | Production ใช้ `uvicorn --workers` ผ่าน `app.serve` (ไม่ใช้ gunicorn); `app.serve` ตรวจ config ก่อน start worker และ exit code 2 เมื่อ config ผิด | gunicorn + `uvicorn-worker` | Accepted (Step 5.1) |
| D-96 | FastAPI เอกสาร `422` เป็น `HTTPValidationError` ของตัวเองเสมอ แต่ app ตอบ Problem Details จริง (`app/api/error_handlers.py`) — `app/api/openapi.py` ห่อ `app.openapi()` แก้ทุก response `422` ให้ชี้ `ProblemResponse` (schema ใหม่ใน `app/schemas/v1/common.py`) แทน ครั้งเดียวทั้งสคีมา | ใส่ `responses={422: ...}` ทีละ route (~30 จุด) | Accepted (Step 5.12) |
| D-97 | `openapi.json` commit ไว้ที่ root ของโมดูล สร้างด้วย `make openapi` (`scripts/export_openapi.py`, ไม่ต้องมี DB/Redis จริง); contract test ตรวจว่าตรงกับ schema ของแอปที่รันอยู่ (`tests/contract/test_openapi_schema.py`) | สร้างใน CI แล้วไม่ commit | Accepted (Step 5.12) |
| D-98 | schemathesis สองชั้น: (1) contract — โหลด schema ที่ export แล้วตรวจโครงสร้างล้วน (`schema.validate()`, ไม่ยิง request จริง) รันทุก push ไม่ต้องมี stack; (2) e2e (`tests/e2e/test_openapi_contract_fuzz.py`) — ยิง fuzz จริงเฉพาะ `GET` ต่อ compose stack จริง เช็คแค่ "ไม่ 5xx" (`not_a_server_error`); ไม่ fuzz POST/PATCH/DELETE เพราะจะไปรบกวนสถานะที่ e2e ไฟล์อื่นใช้ร่วมกัน (เช่นลบบัญชีของ test อื่น) และไปกิน rate limit ต่อ IP (P-31) ของทั้ง suite — งานนี้เคลียร์ key `tsa:*:rl:ip:*` ใน redis-core ทิ้งหลังรันเสมอ | fuzz ทุก method ด้วย mock ทั้งชุด | Accepted (Step 5.12) |
| D-99 | CI เป็น `.github/workflows/api-backend-ci.yml` ที่ root repo (git root คือ monorepo ไม่ใช่โมดูลนี้) กรองด้วย `paths:` ให้ทำงานเฉพาะไฟล์ในโมดูลนี้; job: `lint` (ruff+mypy), `test` (unit+api+integration+contract, Testcontainers ใช้ Docker ของ runner ตรงๆ), `build` (docker build target `runtime` + Trivy scan), `openapi-diff` (oasdiff เทียบ `openapi.json` กับ base branch, เฉพาะ PR, fail เมื่อ breaking), `e2e` (เฉพาะ PR เข้า `develop`) | รอให้ทีมตัดสิน workflow กลางก่อน (item 3 ด้านล่าง) | Accepted (Step 5.12) — ชื่อไฟล์ตั้งใจไม่ชนกับโมดูลอื่น ถ้าทีมมี CI กลางทีหลังค่อยรวม |
| D-100 | stage `base` ใน Dockerfile รัน `apt-get upgrade` ทุกครั้งที่ build เพราะ `python:3.12-slim` ของ upstream ตามหลัง Debian security fix (Trivy เจอ CRITICAL/HIGH ที่มีตัวแก้แล้ว 13 ตัวใน gzip, pcre2, sqlite, perl-base; หลังแก้เหลือ 0); Trivy action ปักที่ `v0.36.0` (tag ของ repo นั้นมี `v` นำหน้า) | ปัก digest ของ base image / รอ upstream rebuild | Accepted (Step 5.12, แก้หลัง CI รอบแรก) |
| D-101 | Keycloak ที่ใช้ร่วมกันทั้งทีมอยู่ใน root `docker-compose.yml` (ไม่ใช่ใน compose ของ 02) เพราะ 01 ต้อง login ผ่านมันด้วย; backend สลับไปตรวจ token ของ Keycloak ด้วย `docker-compose.keycloak.yml` (override) ซึ่งตั้ง `DEV_JWT_SIGNING_KEY=""` (ถ้ามี key นี้ verifier จะใช้แต่ dev key) และ `JWKS_URL` ผ่าน `host.docker.internal` (issuer คือ `localhost:8180` ซึ่ง container เข้าไม่ถึง; ตั้ง `KC_HOSTNAME` ตายตัวให้ `iss` เหมือนกันทุกทาง); scope admin/safety:review อยู่เฉพาะ client `ops-admin` (client credentials) เพื่อให้ user ที่ login ผ่าน `web-app` ขอ scope เหล่านี้ไม่ได้ (ทดสอบแล้วได้ `invalid_scope`); ทดสอบกับ stack จริงแล้ว: user → `/v1/me` 200, user → admin 403, ops-admin → admin 200, ไม่มี token / token ปลอมด้วย dev key / ลายเซ็นผิด → 401 | แก้ default ของ `DEV_JWT_SIGNING_KEY` ใน compose หลัก (กระทบ CI/e2e ที่ใช้ dev token) / Keycloak ใน compose ของ 02 | Accepted (dev) — ก่อน prod: DB จริงแทน H2, HTTPS, admin login รายคนพร้อม role-gated scope แทน client secret ร่วม, ลบ client `dev-cli` |
| D-102 | ผู้ดูแล CI กลางของทั้ง 8 โมดูล คือ **ผู้ดูแลการรวมระบบ (เจ้าของ 02)** — ตอบ item 3 ใน §13; แต่ละโมดูลยังคง workflow แยกของตัวเองไปก่อน (`api-backend-ci.yml` ของ 02 ไม่กระทบใคร, กรองด้วย `paths:`) จนกว่าจะมีการรวมจริง | ให้แต่ละโมดูลดูแล CI ของตัวเองแยกกันถาวร | Accepted (2026-09-20) |

## 13. Open Questions (Phase 4)

1. `FEEDBACK_RETENTION_DAYS` ของ Module 08 = 90 วัน vs P-23 = 180 วัน — ใช้ค่าไหน
2. ทีมจะมี root `docker-compose.yml` ไฟล์เดียวหรือให้แต่ละโมดูลมีของตัวเอง (D-19) — **ตอบไปบางส่วน:** มี root compose แล้วแต่ตอนนี้เก็บเฉพาะ infra ที่ใช้ร่วมกัน (Keycloak, D-101); ยังไม่ได้ตัดสินว่าจะ `include:` stack ของแต่ละโมดูลหรือไม่
3. ~~CI ใช้ GitHub Actions ได้ไหม~~ — ใช้แล้ว (D-99, `.github/workflows/api-backend-ci.yml`, กรองด้วย `paths:`) ~~ที่ยังไม่ตอบคือใครดูแล workflow กลางถ้าทีมอยากรวมของ 8 โมดูลเข้าด้วยกันทีหลัง~~ — **ปิดแล้ว (D-102):** ผู้ดูแลการรวมระบบ (เจ้าของ 02) รับเป็นคนดูแล workflow กลางถ้าทีมอยากรวมทีหลัง
4. `08_monitoring` (Prometheus/Grafana) ใครเป็นเจ้าของ — backend ต้องส่ง scrape config ให้หรือไม่

## 14. Phase 5 — ลำดับการ Implement ที่เสนอ

| Step | งาน | ผลลัพธ์ที่ทดสอบได้ |
|---|---|---|
| 5.1 | Skeleton: pyproject, config, logging, errors, `/health`, Dockerfile, compose (postgres, redis) | `make up` → `/health` = 200 |
| 5.2 | DB models + Alembic 0001–0007 + seed | migration up/down ผ่าน |
| 5.3 | Auth (dev issuer + JWKS), request context, error handlers, rate limit, idempotency | API tests: 401/403/422/429/409 |
| 5.4 | Mock Agent + AgentClient (timeout, retry, circuit breaker) | respx tests ทุก error mapping |
| 5.5 | Domain: normalization, freshness, safety gate, sanitizer | unit tests R-01..R-07 |
| 5.6 | Recommendation flow: service + Celery task + job state + SSE (+ stream ticket, cache, JIT user แบบย่อ) | E2E: 200 / 202 + events — **done** |
| 5.7 | Conversations + follow-up, `GET /v1/travel/recommendations` (E-02, cursor) | ครบ E-02, E-08..E-13 — **done** |
| 5.8 | Trips + alerts, feedback + review queue (+ beat container, audit writer) | E-14..E-19 และ review queue — **done** |
| 5.9a | Me: profile / consent / ลบบัญชี, reaper, `DELETE /v1/jobs/{id}` (E-05), `prediction_records` | E-05, E-20 — **done** |
| 5.9b | Data export (E-21/E-22, MinIO), purge job (P-50), partition audit รายเดือน, column encryption (D-15) | E-21, E-22 — **done** |
| 5.10 | Observability (OTel, metrics), `/ready`, service-status | E-23, E-26, E-27 + trace HTTP → Celery → Agent — **done** |
| 5.11 | Admin endpoints | E-24 ครบ (jobs, recommendation, audit log, training export) — **done** |
| 5.12 | OpenAPI export, contract tests, CI | openapi.json + snapshot/structural/live-fuzz contract tests + GitHub Actions — **done** |

## 15. Change Log

| Version | วันที่ | รายละเอียด |
|---|---|---|
| 0.17 | 2026-09-20 | D-102: ผู้ดูแลการรวมระบบ (เจ้าของ 02) รับดูแล CI กลางถ้าทีมรวม workflow ของ 8 โมดูลทีหลัง — ปิด §13 item 3 |
| 0.16 | 2026-09-19 | D-04: ปิด Q3 — SSE เป็นช่องทางเดียว, WS (E-07) descoped ก่อนส่งงาน เพราะโจทย์อาจารย์ระบุ "WebSocket/SSE" เป็นทางเลือก; trip live alert อ่านด้วย polling |
| 0.15 | 2026-09-19 | D-01 → Keycloak (dev), D-101, `docker-compose.keycloak.yml`; root `docker-compose.yml` + `identity/keycloak/realm-travel-safety.json` (repo root) |
| 0.14 | 2026-09-18 | Step 5.12: D-96..D-99, `app/api/openapi.py` + `app/schemas/v1/common.py` (ProblemResponse แทน HTTPValidationError), `scripts/export_openapi.py` + `openapi.json`, `make openapi`, `tests/contract/test_openapi_schema.py`, `tests/e2e/test_openapi_contract_fuzz.py`, `.github/workflows/api-backend-ci.yml` (repo root) |
| 0.1 | 2026-09-17 | Draft แรก |
| 0.2 | 2026-09-17 | Step 5.1: เปลี่ยนจาก gunicorn เป็น `app.serve` + uvicorn workers (D-25) |
| 0.13 | 2026-09-18 | Step 5.11: D-92..D-95, ไฟล์ admin (access / jobs / recommendations / audit / exports), admin_service, training_export_service, migration `0010` |
| 0.12 | 2026-09-18 | Step 5.10: D-87..D-91, ไฟล์ ops_service / service_status / health / signals, service `jaeger` แทน otel-collector + jaeger |
| 0.11 | 2026-09-18 | Step 5.9b: D-81..D-86, ไฟล์ encryption / types / exports / retention / cooldown / object store, service `minio` |
| 0.10 | 2026-09-18 | Step 5.9a: D-72..D-80, ไฟล์ profile / prediction / me / account / reaper / maintenance, queue `maintenance`; แบ่ง 5.9 เป็น 5.9a / 5.9b |
| 0.9 | 2026-09-17 | Step 5.8: D-59..D-71, ไฟล์ trips / feedback / audit / alert scan, container `beat` (ย้ายจาก 5.9), queue `alerts` |
| 0.8 | 2026-09-17 | Step 5.7: D-52..D-58, ไฟล์ `follow_up.py`, `pagination.py`, `conversation_service.py`, repositories ใหม่ |
| 0.7 | 2026-09-17 | Step 5.6: D-37..D-51 (D-23 แทนด้วย D-37), ไฟล์ใหม่ใน tree, งานที่เลื่อนไป 5.7 / 5.9 |
| 0.6 | 2026-09-17 | Step 5.5: D-34..D-36, `tests/unit/domain/test_layering.py` ตรวจ layer rule ของ domain (แทน import-linter ชั่วคราว) |
| 0.5 | 2026-09-17 | Step 5.4: เพิ่ม D-31..D-33, D-24 Accepted, mock agent ไม่มี Dockerfile แยก |
| 0.4 | 2026-09-17 | Step 5.3: D-22 เปลี่ยนเป็น joserfc, เพิ่ม D-28..D-30, ไฟล์ `api/auth.py`, `api/idempotency.py`, `api/resources.py` |
| 0.3 | 2026-09-17 | Step 5.2: ปรับชื่อไฟล์ models ตามที่ implement จริง, เพิ่ม D-26, D-27 |
