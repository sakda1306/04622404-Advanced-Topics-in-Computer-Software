# 11 — Decisions and lessons

> Paths are relative to `DL-07-Agentic-AI-System-II/`. "Stated" = the reason is written in code/docs. "Inferred" = my reading of the code.

## Decisions

| Decision | Alternative not taken | Rationale | Evidence |
|---|---|---|---|
| Rules decide, LLM only explains a locked action | LLM chooses the action | A wrong "safe" answer can hurt someone (stated) | `README.md` Summary, `02_api_backend/app/domain/safety_gate.py:3-5`, `07_decision_llm_engine/decision_engine/explanation.py:64` |
| LLM output must match a sentence bank, else template | Free-text LLM with post-filters | Cannot invent numbers, citations, instructions (stated) | `explanation.py:15-20`, `91-98` |
| API never calls the Agent; Celery worker does (D-03) | Call Agent inside the request | Bounded request time, retries/cancel outside HTTP, one place for the Safety Gate (stated partially, rest inferred) | `02_api_backend/app/services/recommendation_service.py:3-5` |
| `mode=auto`: wait up to 8 s, then 202 + job | Always async / always sync | Fast answers stay simple; slow ones degrade to polling/SSE (inferred) | `recommendation_service.py:371-394`, `02_api_backend/README.md` |
| Job events in Redis Streams, DB is source of truth | Pub/Sub only, or DB polling | Replay with `Last-Event-ID`, survives reconnect; Redis loss is not data loss (stated) | `02_api_backend/app/infrastructure/redis/job_state.py:5` |
| SSE with single-use ticket | Token in query string, WebSocket | `EventSource` cannot send headers (stated D-06) | `02_api_backend/app/api/v1/jobs.py:131` |
| Two Redis instances (core AOF/noeviction, cache LRU no-persist) | One Redis | Cache eviction must not drop rate limits / jobs (inferred, D-14 referenced) | `02_api_backend/docker-compose.yml`, `app/core/config.py:80` |
| Circuit breaker state in Redis, fail-open | Per-process breaker | Shared across API + worker processes; breaker must not cause outages (stated) | `app/infrastructure/agent/circuit_breaker.py:1-9` |
| Rate limiter fails open | Fail closed | Availability over strictness (inferred; configurable) | `app/api/auth.py:42-46` |
| RFC 9457 Problem Details everywhere, stable `code` | FastAPI default errors | One error shape for the web team; never echo input (stated) | `app/api/problem.py:1`, `app/api/error_handlers.py:29` |
| Mandatory `Idempotency-Key` on POST | Optional | Safe retries of expensive POSTs (inferred) | `app/api/idempotency.py:47-54` |
| Ports/Protocols + `deps.py` as only wiring point | Direct imports | Testability with fakes; layering enforced by test (stated) | `app/api/deps.py:1`, `tests/unit/domain/test_layering.py` |
| Settings validated before uvicorn starts | Fail inside worker import | Avoid "container up but never healthy" loops (stated) | `app/serve.py:1-6` |
| Tool failure ⇒ `UNAVAILABLE` + partial result | Fail the whole run | One provider cannot take the whole answer down (stated) | `03_travel_ai_agent/travel_agent/pipeline.py:216-217` |
| Missing data never means "safe" (R-02, INSUFFICIENT_EVIDENCE) | Default to low risk | Stated in 02 and 07 | `safety_gate.py:174-177`, `07_decision_llm_engine/README.md` |
| Retrieval returns empty rather than generic advice | Generic fallback text | No fabricated emergency procedures (stated) | `06_risk_knowledge_services/risk_knowledge/knowledge.py:73-77` |
| Policy, prompt and escalation rules locked by validators | Env-tunable | Changes need a reviewed release (stated) | `07_decision_llm_engine/decision_engine/config.py:27-70` |
| Cache only non-personal, non-HIGH, fresh results; geohash cells + time bucket | No cache / exact-key cache | Share safe results across users without leaking questions (inferred from code) | `app/domain/cache_policy.py:21-55` |
| Column encryption for free text, keyed hashes for ids | Plain text | PDPA-style privacy (inferred; D-15/D-81 referenced) | `app/core/encryption.py:1-8` |
| OpenAPI snapshot committed + CI drift/breaking check | Generate on demand | Contract for the frontend team (stated) | `02_api_backend/README.md` "OpenAPI contract and CI" |
| 03 imports 04/05/06 in-process from sibling folders | Separate HTTP services | Faster to integrate a student project (inferred) | `03_travel_ai_agent/travel_agent/tools/live.py:44-111` |

## Weak spots / tech debt

| Issue | Evidence |
|---|---|
| No LLM is actually integrated; planner and explainer are rules/templates | `03_travel_ai_agent/travel_agent/config.py:9`, `07_decision_llm_engine/decision_engine/api.py:27` |
| No RAG corpus, no embeddings; live agent passes zero passages ⇒ knowledge always empty | `03_travel_ai_agent/travel_agent/tools/live.py:241`, `06_risk_knowledge_services/README.md` |
| Weather + route candidates still mock in live mode | `03_travel_ai_agent/README.md` status table |
| Module 08 duplicates 02's recommendation storage + feedback with a different schema and no auth | `08_recommendation_feedback/app/main.py:83-188`, `db_schema.sql` vs `02_api_backend/app/infrastructure/db/models/mlops.py` |
| Contracts copied between modules by hand (`contracts.py` in 02 and 03) | `03_travel_ai_agent/README.md` "02 (sakda)" note |
| Confidence semantics disagree (07 policy score vs 02 risk confidence); 03 sends `null` | `03_travel_ai_agent/README.md` "07" note |
| No combined compose; port 8010 clash between mock-agent and travel-agent | `/docker-compose.yml` header, compose files |
| 04 uses blocking `urlopen` (sync) and no cache despite `CACHE_TTL` env name | `04_external_data_services/open_meteo_adapter.py:32`, `/.env.example` |
| 07 audit is a local JSONL file (no rotation) | `07_decision_llm_engine/decision_engine/audit.py:28-48` |
| Frontend: hand-written types, admin page uses hard-coded numbers, silent mock fallback, token from sessionStorage, no frontend tests | `01_web_app/lib/types.ts`, `app/admin/page.tsx`, `components/trip-context.tsx:104-111`, `lib/api/client.ts:13-19` |
| Thai tokenisation is regex only (no word segmentation) ⇒ weak BM25 on Thai text | `06_risk_knowledge_services/risk_knowledge/knowledge.py:25` |
| Token budget measured in bytes, not tokens | `07_decision_llm_engine/decision_engine/explanation.py:73-77` |
| 02 is heavy for a 6-day MVP: Postgres+PostGIS, 2× Redis, MinIO, Celery, Keycloak, OTel | `02_api_backend/docker-compose.yml` |
| 08 dependencies unpinned | `08_recommendation_feedback/requirements.txt` |

## Copy as-is vs change

| Copy as-is | Change / simplify |
|---|---|
| Problem Details error model + handlers (`app/core/errors.py`, `app/api/problem.py`, `app/api/error_handlers.py`) | Drop Postgres-specific bits (PostGIS, partitions, ARRAY, JSONB) → SQLite JSON |
| `apiFetch` + `ApiError` (`01_web_app/lib/api/client.ts`, `problem.ts`) | Replace Celery with FastAPI `BackgroundTasks` / an asyncio task for MVP |
| Sliding-window Lua rate limiter (needs Redis) **or** port the idea to SQLite | Replace Keycloak/JWKS with a simple session cookie or anonymous user id |
| Cooldown `SET NX EX` → daily quota counter | One Redis (or none) instead of core + cache + MinIO |
| Settings groups + fail-fast `serve.py` | Explanation grounding: relax exact-match to "ids and numbers subset" |
| Logging redaction processor | BM25 → Chroma + multilingual embeddings; keep the filters + rerank |
| Tool bulkhead `_call` (timeout + mark unavailable + continue) | Agent budget → simpler per-route timeout |
| `ExplanationProvider` Protocol + `Candidate` schema + retry-in-timeout + template fallback | Policy JSON → role-matching weights JSON |
| Versioned templates TH/EN | — |
| Layering test (AST import check) | — |
| Mock scenarios behind same interface (`MockToolSet`, `mock_agent`) | — |
