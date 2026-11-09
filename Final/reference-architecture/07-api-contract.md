# 07 — API contract

> Paths are relative to `DL-07-Agentic-AI-System-II/`. Full machine-readable contract for 02: `02_api_backend/openapi.json` (written by `scripts/export_openapi.py`, drift checked by `tests/contract/test_openapi_schema.py`). Human spec: `02_api_backend/docs/02_api_spec.md`.

## Shared conventions (02)

| Concern | Rule | File |
|---|---|---|
| Base path | `/v1` | `02_api_backend/app/api/v1/router.py:22` |
| Auth | `Authorization: Bearer <JWT>`; verified via JWKS (`JWKS_URL` or issuer discovery) or dev HS256 key in dev/test only; per-route scopes `travel:read`, `travel:write`, `profile:read`, `profile:write`, `admin:read`, `admin:write`, `safety:review` | `app/api/auth.py:18-23`, `app/core/security.py:35-42`, `02_api_backend/README.md` |
| User identity | Principal `(issuer, subject)` → `users` row; Redis keys use keyed hash, never raw subject | `app/api/deps.py:59-68`, `app/api/auth.py:25-29` |
| Idempotency | Every POST on idempotent routers **requires** `Idempotency-Key` (8–128 chars `[A-Za-z0-9._:-]`); same key + different body ⇒ 409 `IDEMPOTENCY_CONFLICT`; concurrent ⇒ 409 `IDEMPOTENCY_IN_PROGRESS`; replay adds `Idempotent-Replayed: true`; only 2xx stored, 24 h | `app/api/idempotency.py:1-60`, `config.py:228` |
| Rate-limit headers | `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`; 429 adds `Retry-After` | `app/infrastructure/redis/rate_limiter.py:34-45` |
| PATCH | `application/merge-patch+json` (JSON Merge Patch) | `02_api_backend/README.md` (trips, me) |
| Pagination | `?limit=&cursor=` → `{items, next_cursor}`; max page 50 | `app/services/pagination.py`, `config.py:206` |
| Language | `Accept-Language` header or body `language` | `app/api/v1/recommendations.py:50-55` |
| Not-yours = not-found | Other users' resources return 404 | `app/services/recommendation_service.py:231-240` |
| Tracing headers | `X-Request-ID`, `X-Correlation-ID` (accepted and echoed) | `app/main.py:91-93` |

### Error shape (RFC 9457, `application/problem+json`)

```json
{
  "type": "https://errors.<base>/validation-error",
  "title": "…", "status": 422, "code": "VALIDATION_ERROR",
  "detail": "…", "instance": "/v1/travel/recommendations",
  "request_id": "…", "correlation_id": "…",
  "errors": [{"field": "origin.lat", "message": "…", "code": "…"}]
}
```
`app/api/problem.py:15-38`, `app/schemas/v1/common.py:18-35`. Codes and statuses: `app/core/errors.py:10-93` (table in `02-request-flow.md`).

### Async result shape (202)

```json
{"job_id": "…", "status": "queued", "recommendation_id": "…", "conversation_id": "…",
 "events_url": "/v1/jobs/{id}/events", "status_url": "/v1/jobs/{id}"}
```
`app/schemas/v1/travel.py:266-272`, `app/api/v1/responses.py`.

---

## 02 API backend endpoints

```
POST /v1/travel/recommendations?mode=auto|sync|async
Purpose: ask for a recommendation
Request: TravelRequest {origin{lat,lon,name?,place_id?}, destination, waypoints[], departure_time, timezone, language?, preferences{travel_modes[],avoid[],max_travel_hours?,mobility_needs[],traveler_count}, question?, conversation_id?, trip_id?} + Idempotency-Key; scope travel:write
Response 200: RecommendationResponse {recommendation_id, conversation_id, request_id, status, created_at, valid_until, language, risk{level,score,confidence,factors[]}, recommendation{type,summary,reasons[],suggested_departure_time}, routes{primary,alternatives[]}, hazards[], emergency_instructions?, sources[], data_freshness, service_status{}, clarification?, warnings[], versions, disclaimer, job_id?, error?}
Response 202: JobAccepted (auto: still running after 8 s; async: always)
Errors: 400, 401, 403, 404 (conversation/trip), 409 idempotency, 413, 422 VALIDATION_ERROR/UNSUPPORTED_REGION, 429 RATE_LIMITED/TOO_MANY_ACTIVE_JOBS, 502, 503, 504 AGENT_TIMEOUT (sync)
```
`app/api/v1/recommendations.py:37-64`, `app/schemas/v1/travel.py:53-64`, `214-237`

```
GET /v1/travel/recommendations?limit&cursor&from&to&risk_level
Purpose: history, newest first
Request: query only; scope travel:read
Response 200: {items: RecommendationSummary[], next_cursor}
Errors: 401, 403, 422
```
`app/api/v1/recommendations.py:67-93`

```
GET /v1/travel/recommendations/{recommendation_id}
Purpose: one recommendation
Response 200: RecommendationResponse
Errors: 401, 403, 404
```
`app/api/v1/recommendations.py:96-107`

```
GET /v1/jobs/{job_id}
Purpose: job status
Response 200: {job_id, type, status, stage, progress, created_at, updated_at, result_url, error{code,message}?}
Errors: 401, 403, 404
```
`app/api/v1/jobs.py:72-83`, `app/schemas/v1/jobs.py:24-33`

```
DELETE /v1/jobs/{job_id}
Purpose: cancel a running job (worker stops the Agent run)
Response 202: JobResponse
Errors: 404, 409 JOB_NOT_CANCELLABLE
```
`app/api/v1/jobs.py:86-100`

```
POST /v1/jobs/{job_id}/stream-ticket
Purpose: single-use ticket for EventSource
Response 200: {ticket, expires_in}
Errors: 401, 403, 404
```
`app/api/v1/jobs.py:103-115`

```
GET /v1/jobs/{job_id}/events?ticket=…   (or Bearer header)   Last-Event-ID optional
Purpose: SSE progress stream
Response 200: text/event-stream; events "progress" {job_id,stage,progress,message,at}, terminal "completed" {job_id,status,result_url} | "failed" {job_id,error} | "cancelled"; heartbeats
Errors: 401/403 (bad ticket), 404, 429 (too many streams)
```
`app/api/v1/jobs.py:118-152`, `app/services/recommendation_service.py:326-336`, `app/services/agent_run_service.py:290-299`

```
POST /v1/conversations
Purpose: start a conversation
Request: {title?, language?} + Idempotency-Key
Response 201: {conversation_id, title, language, created_at, updated_at, last_recommendation_id, message_count}
Errors: 401, 403, 422
```
`app/api/v1/conversations.py:38-60`, `app/schemas/v1/conversations.py:19-32`

```
GET /v1/conversations | GET /v1/conversations/{id} | DELETE /v1/conversations/{id}
Purpose: list (paged) / get / delete (204, cascades messages)
Errors: 401, 403, 404
```
`app/api/v1/conversations.py:63-104`

```
GET /v1/conversations/{id}/messages?limit&cursor
Purpose: messages newest first
Response 200: {items: [{message_id, role, content, recommendation_id, created_at}], next_cursor}
```
`app/api/v1/conversations.py:107-124`, `app/schemas/v1/conversations.py:59-79`

```
POST /v1/conversations/{id}/messages
Purpose: ask a (follow-up) question
Request: {content ≤20000, overrides: TravelOverrides, stream: bool=false} + Idempotency-Key
Response 200: MessageResponse (assistant reply linked to recommendation)
Response 202: JobAccepted (stream=true or slow)
Errors: 404, 422 (empty content / bad overrides), 429, 503, 504
```
`app/api/v1/conversations.py:127-153`, `app/services/conversation_service.py:116-166`

```
POST /v1/trips | GET /v1/trips | GET /v1/trips/{id} | PATCH /v1/trips/{id} | DELETE /v1/trips/{id}
Purpose: saved trips with live-alert consent
Request (POST): {name, origin, destination, waypoints[], departure_time, timezone, preferences, alerts{enabled, consent_at, channels[]}}
Response: TripResponse {trip_id, …, alerts, status, last_assessment{recommendation_id,status,risk_level,recommendation_type,created_at,outdated}}
Errors: 404, 409, 422
```
`app/api/v1/trips.py:36-114`, `app/schemas/v1/trips.py:36-216`

```
POST /v1/trips/{id}/assessments | GET /v1/trips/{id}/assessments
Purpose: assess now (same outcome as recommendations) / list assessments
Request: {mode?, language?}
Response 200: RecommendationResponse | 202 JobAccepted
```
`app/api/v1/trips.py:117-160`

```
POST /v1/recommendations/{id}/feedback
Purpose: rate or report
Request: {rating?, helpful?, outcome, report_type?, comment? ≤20000} + Idempotency-Key
Response 201: {feedback_id, created_at, review_status}
Errors: 404, 409, 422
```
`app/api/v1/feedback.py:20-40`, `app/schemas/v1/feedback.py:20-41`

```
GET /v1/me | PATCH /v1/me | DELETE /v1/me
Purpose: profile + consents (live_alerts, analytics) / merge-patch / delete account (202, background)
Scopes: profile:read / profile:write
```
`app/api/v1/me.py:24-70`, `app/schemas/v1/me.py:23-29`

```
POST /v1/me/data-export | GET /v1/me/data-export/{id}
Purpose: export my data (once per 24 h) / status + 15-min download URL
Response: 202 / 200
Errors: 429 RATE_LIMITED with Retry-After, 503
```
`app/api/v1/exports.py:58-90`

```
GET /v1/service-status
Purpose: public per-service status (ok/degraded/unavailable/unknown) from Agent reports in last 15 min
Response 200: {status, updated_at, components{name: state}, message}
```
`app/api/v1/service_status.py:21-30`

```
GET /v1/admin/jobs | GET /v1/admin/recommendations/{id} | GET /v1/admin/audit-logs
POST /v1/admin/exports/training-data | GET /v1/admin/exports/training-data/{id}
GET /v1/admin/feedback/reviews | PATCH /v1/admin/feedback/reviews/{feedback_id}
Purpose: diagnostics without PII, audit, training export, safety review
Scopes: admin:read / admin:write / safety:review; refusals audited as "denied"
```
`app/api/v1/admin/*.py`, `02_api_backend/README.md` "Admin tools"

```
GET /health        → 200 {"status":"ok"} (liveness, no dependency checks)
GET /ready         → 200/503 {status, checks{}} (internal networks only, else 404)
GET /metrics       → Prometheus text (internal only)
```
`app/api/ops.py:32-95`

## Internal service endpoints

```
POST /v1/agent/runs            (03, also mock_agent)
Purpose: run the agent
Request: AgentRunRequest {run_id, intent_hint, request{origin,destination,departure_time,timezone,language,preferences,question}, context{messages[]}, user_profile{pseudonymous_id,language,home_region}, limits{deadline_at,max_tool_calls}}; headers Authorization, X-Deadline, Accept (application/json | application/x-ndjson)
Response 200: AgentRunResponse JSON, or NDJSON progress lines then final line
Errors: 401, 422, 503 DECISION_UNAVAILABLE / DECISION_MISMATCH
DELETE /v1/agent/runs/{run_id} → 202
GET /health, GET /ready
```
`03_travel_ai_agent/travel_agent/api.py:102-224`, `03_travel_ai_agent/tests/conftest.py:13-34`, `02_api_backend/mock_agent/main.py:89-143`

```
POST /v1/decisions             (07)
Purpose: deterministic decision + explanation
Request: DecisionRequest (evidence, risk, routes, alerts, quality, locale)
Response 200: DecisionResponse {request_id, action_code, rules_fired, confidence, confidence_kind, evidence_status[], explanation{summary,reasons,instructions,uncertainty,mode}, versions, escalation_reasons, validation_results, …}
Errors: 422
```
`07_decision_llm_engine/decision_engine/api.py:30-70`, `decision_engine/models.py`

```
08: GET /recommendation/mock/{scenario}, GET /recommendation/{request_id}, POST /recommendation/generate,
    POST /feedback, GET /feedback/safety-queue, POST /feedback/{request_id}/review, POST /feedback/cleanup, GET /health
```
`08_recommendation_feedback/app/main.py:83-188` (no auth found on these routes).

## How the frontend calls the API

| Piece | Detail | File |
|---|---|---|
| Fetch wrapper | `apiFetch<T>(path, {body, rawBody, idempotencyKey, searchParams, ...})`; sets `Accept`, `Accept-Language`, Bearer token, UUIDv7 `Idempotency-Key` on POST, JSON body | `01_web_app/lib/api/client.ts:55-107` |
| Token source | `sessionStorage.access_token` or `NEXT_PUBLIC_DEV_TOKEN`; single function to swap for Keycloak later | `client.ts:13-19` |
| Errors | `ApiError(status, ProblemDetails)`; network failure ⇒ status 0 `network_error`; non-JSON error ⇒ status text | `client.ts:90-117`, `lib/api/problem.ts` |
| Typed surface | `api.createRecommendation`, `getRecommendation`, `getServiceStatus`, `getAdminJobs`, `getFeedbackReviews` | `lib/api/index.ts` |
| SSE | `followRecommendationJob(accepted)` → ticket → `EventSource` → resolve on `completed` | `lib/api/index.ts` |
| Types | Hand-written TS types (not generated from `openapi.json`) | `01_web_app/lib/types.ts` |
| Shape drift handling | `api.getServiceStatus` is typed `{services:[{name,status}]}`, but the backend returns `{status, updated_at, components, message}`. The status page avoids this by using a tolerant `normalize()` that accepts arrays or keyed objects | `lib/api/index.ts`, `lib/api/service-status.ts:32-90`, `02_api_backend/app/api/v1/service_status.py:21-27` |
