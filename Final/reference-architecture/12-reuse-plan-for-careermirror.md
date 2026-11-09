# 12 — Reuse plan for CareerMirror

> Paths are relative to `DL-07-Agentic-AI-System-II/`. Target stack: Next.js App Router (TS), FastAPI, Groq (model name in env), Chroma + local multilingual embeddings, SQLite, Docker Compose.

## Mapping

| Pattern in this repo | CareerMirror equivalent | Verdict | Notes |
|---|---|---|---|
| App factory + lifespan-owned resources (`02_api_backend/app/main.py:33-114`, `app/api/resources.py`) | FastAPI app owning SQLite engine, Chroma client, Groq client, embedder | Reuse as-is | Load the embedding model once in lifespan |
| Grouped settings + fail-fast `serve.py` (`app/core/config.py`, `app/serve.py:33-67`) | `GROQ_API_KEY`, `GROQ_MODEL`, `EMBEDDING_MODEL`, `CHROMA_PATH`, `SQLITE_PATH`, `DAILY_LLM_QUOTA`, `JOB_PROVIDER_*` | Reuse as-is | Keep `SecretStr` + error output without values |
| Problem Details errors (`app/core/errors.py`, `app/api/problem.py`, `app/api/error_handlers.py`) | Same, add codes `QUOTA_EXCEEDED`, `CV_UNREADABLE`, `FILE_TOO_LARGE`, `LLM_UNAVAILABLE` | Reuse as-is | Thai `detail` via `Accept-Language` |
| Router → service → ports → infrastructure + `deps.py` (`app/api/deps.py`, `app/services/ports.py`) | `routers/`, `services/`, `repositories/` (SQLite), `clients/` (Groq, Chroma, job provider) | Adapt | Fewer layers; keep `deps.py` as the only wiring point |
| Domain purity test (`tests/unit/domain/test_layering.py`) | Keep `scoring/` (role matching) free of FastAPI/DB/LLM imports | Reuse as-is | Directly protects "scoring in plain Python" |
| Body guard middleware (`app/api/middleware/body_guard.py`) | Upload size limit for CV PDF (e.g. 5 MB) + JSON limit elsewhere | Adapt | Allow `multipart/form-data` only on `/cv` |
| CV PDF upload/parse | — | Not in repo | Build new; store file path + parsed text in SQLite |
| Questionnaire form (`01_web_app/components/travel-form.tsx`) | Questionnaire steps with zod + RHF, Thai messages | Adapt | — |
| Conversation + follow-up merge (`app/services/conversation_service.py:116-166`, `app/domain/follow_up.py:101`) | Chat that updates the profile draft; each message carries profile `overrides` | Adapt | Profile completeness = share of required fields filled (new pure function) |
| Intent hint enum + "ask instead of guess" (`app/infrastructure/agent/contracts.py:36-40`, `03_travel_ai_agent/travel_agent/pipeline.py:254-279`) | AI Router enum: `SKILL_ASSESSMENT, WORK_STYLE, BLIND_SPOTS, JOB_MATCHING, SALARY, MARKET, EXPERIENCE, PROFILE_EDIT` + `CLARIFY` | Adapt | Router = Groq JSON-mode classify → validate with Pydantic `Literal` → one handler; invalid ⇒ `CLARIFY` |
| Tool allowlist + bulkhead `_call` (`03_travel_ai_agent/travel_agent/tools/base.py:27-38`, `pipeline.py:208-241`) | Handler registry: exactly one route per request, per-route timeout, failure ⇒ degraded answer | Reuse as-is (pattern) | — |
| Deterministic decision table (`07_decision_llm_engine/decision_engine/policy.py:171-192`, `policies/prototype-v3.json`) | Role-match scoring weights in JSON, versioned; plain Python scorer | Adapt | Store `scoring_version` with each result |
| LLM explains a locked result (`explanation.py:52-122`) | Groq explains match score; must cite only supplied role/evidence ids and numbers | Adapt | Relax exact-match: check ids ⊆ supplied, numbers ⊆ input, score unchanged |
| Template fallback + flags (`explanation.py:35-49`, `templates/v1.json`) | Thai template explanation when Groq fails / quota exceeded | Reuse as-is | Mark response `degraded: ["llm"]` |
| Byte-length token budget (`explanation.py:73-77`) | Token budget before Groq call | Adapt | Use a real tokenizer or conservative chars/token for Thai |
| BM25 + filters + rerank (`06_risk_knowledge_services/risk_knowledge/knowledge.py:64-148`) | Chroma query with `where` filters (role, language, approved), then same hybrid rerank, `min_score`, `top_k` | Adapt | Keep "empty = not enough evidence" |
| Citation excerpt format (`knowledge.py:133-137`) | `[doc_id; section; score]` in context, ids returned as `sources[]` | Reuse as-is | — |
| Passage schema (`risk_knowledge/models.py:195-215`) | RoleDocument chunk metadata | Adapt | Add chunker + seed script (not in repo) |
| Provider adapter returning explicit `unavailable` record (`04_external_data_services/weather_service.py:32-66`) | Job-data provider adapter | Reuse as-is (pattern) | — |
| Recommendation cache key + TTL rules (`app/domain/cache_policy.py`) | Per-role job-data cache key `jobs:{role_id}:{region}` with `fetched_at`, `expires_at` | Adapt | Repo has **no** "serve stale on failure"; add it |
| Freshness check on read (`app/services/recommendation_service.py:266-277`) | Mark job data `is_stale` in response | Adapt | — |
| Celery beat refresh (`app/workers/schedule.py`) | Background refresh of role caches | Don't reuse | Use an asyncio loop in lifespan (as `08_recommendation_feedback/app/main.py:44-60`) or APScheduler |
| Celery job + Redis Streams + SSE + tickets (`app/services/recommendation_service.py`, `app/api/v1/jobs.py`) | Chat streaming | Don't reuse | Stream Groq tokens directly via `StreamingResponse` (SSE) on the same request; no queue needed for MVP |
| SSE client wrapper (`01_web_app/lib/api/index.ts`) | Chat stream reader | Adapt | Use `fetch` + `ReadableStream` (POST with body) instead of `EventSource` |
| Sliding-window rate limiter (`app/infrastructure/redis/rate_limiter.py`) | Per-minute abuse limit | Adapt / optional | Without Redis, a SQLite counter or in-memory limiter is enough for MVP |
| Cooldown `SET NX EX` (`app/infrastructure/redis/cooldown.py:15-20`) | **Daily LLM quota per user** checked before every Groq call | Adapt | SQLite table `llm_usage(user_id, day, count)` with atomic `UPDATE … WHERE count < limit`; 429 + `Retry-After` until midnight Asia/Bangkok |
| Idempotency-Key (`app/api/idempotency.py`) | CV upload + profile edits | Don't reuse (MVP) | Nice-to-have later |
| JWT/JWKS + Keycloak + scopes | Auth | Don't reuse | Anonymous session id cookie or simple email login |
| Column encryption + logging redaction (`app/core/encryption.py`, `app/core/logging.py:15-60`) | CV text is PII | Adapt | At least copy the log redaction list (+ `cv_text`, `phone`, `email`); encryption optional |
| Retention `expires_at` + purge | Delete CVs after N days | Adapt | Simple daily cleanup loop |
| `apiFetch` + `ApiError` (`01_web_app/lib/api/client.ts`, `problem.ts`) | Frontend API client | Reuse as-is | Swap token source; `rawBody: FormData` for CV |
| Trip context status machine + seq guard (`01_web_app/components/trip-context.tsx:39-111`) | Chat/profile context | Adapt | Remove silent mock fallback |
| React Query defaults (`01_web_app/components/providers.tsx`) | Same | Reuse as-is | — |
| Mock implementations behind the interface (`03_travel_ai_agent/travel_agent/tools/mocks.py`, `02_api_backend/mock_agent/`) | `FakeGroq`, `FakeJobProvider` with scenarios | Reuse as-is (pattern) | Essential for tests without quota |
| Testing stack (httpx ASGITransport, fakes, contract tests) | Same with SQLite tmp file | Reuse as-is | Drop Testcontainers |
| Multi-stage Dockerfiles, non-root, healthchecks, `depends_on: service_healthy`, `read_only` + `cap_drop` | `web`, `api` (+ volume for SQLite, Chroma, uploads) | Reuse as-is | Two services is enough |
| Postgres/PostGIS, MinIO, Jaeger, Prometheus, Keycloak | — | Don't reuse | Out of MVP scope |

## Code worth copying (paths)

1. `02_api_backend/app/core/errors.py` + `app/api/problem.py` + `app/api/error_handlers.py` — whole error stack.
2. `02_api_backend/app/serve.py` — config validation before start.
3. `02_api_backend/app/core/config.py:18-70` — settings-group pattern (trim groups).
4. `02_api_backend/app/core/logging.py` — redaction processor.
5. `02_api_backend/app/api/middleware/body_guard.py` — adapt for upload size.
6. `02_api_backend/app/infrastructure/redis/cooldown.py` — model for the quota check (port to SQLite).
7. `03_travel_ai_agent/travel_agent/pipeline.py:208-241` — `_call` bulkhead.
8. `03_travel_ai_agent/travel_agent/tools/base.py:27-55` — allowlist + Protocol toolset.
9. `07_decision_llm_engine/decision_engine/explanation.py` — provider seam, structured candidate, timeout-wrapped retries, fallback flags.
10. `07_decision_llm_engine/decision_engine/policy.py:171-192` — first-match rule table.
11. `06_risk_knowledge_services/risk_knowledge/knowledge.py:99-148` — filter → score → rerank → cite.
12. `04_external_data_services/weather_service.py:32-66` — explicit unavailable record.
13. `02_api_backend/tests/unit/domain/test_layering.py` — import-boundary test.
14. `01_web_app/lib/api/client.ts` + `lib/api/problem.ts` — frontend client.
15. `01_web_app/components/providers.tsx` — React Query retry policy.

## Suggested build order — 6-day MVP

| Day | Goal | Reused pieces |
|---|---|---|
| 1 | Skeleton: compose (`web`, `api`), FastAPI factory + settings + Problem Details + logging redaction, SQLite models (users, profiles, cv_files, messages, llm_usage, role_cache), Next.js shell + `apiFetch` | items 1–4, 14, 15; 02 Dockerfile pattern |
| 2 | CV upload (size/type guard, PDF text extraction) + questionnaire → Profile Builder (pure function merging CV + answers + chat edits) + completeness meter | item 5; follow-up merge idea; form pattern |
| 3 | Groq client behind a Provider Protocol, daily quota check before every call, template fallback; AI Router (enum + JSON-mode classify + validate + `CLARIFY`) with handler registry | items 6–9 |
| 4 | Role documents → chunker → Chroma seed script with local multilingual embeddings; retrieval with filters + rerank + citations | item 11 |
| 5 | Role matching scorer in plain Python (versioned weights JSON, layering test) + LLM explanation of locked score; job-data provider adapter with per-role cache, background refresh loop, stale fallback | items 10, 12, 13 |
| 6 | Chat streaming UI with completeness meter, remaining routes (salary/market via cached job data), fakes for Groq and job provider, API tests, Docker healthchecks, README | mock-scenario pattern, testing stack |
