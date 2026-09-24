# Step 5.9a — Profile, Consent, Account Deletion, Job Cancel, Reaper and Prediction Records Implementation Plan

**Goal:** Users can read and change their profile and consents, delete their account, and cancel a running job; stuck jobs are closed by a scheduled reaper; successful assessments of users who agreed to analytics are copied, anonymized, to `prediction_records`.

**Architecture:** Same layers as 5.6–5.8. Cancellation is recorded in PostgreSQL first; the worker watches the job row while it waits for the Agent and cancels the Agent run. A finished job never overwrites a job that was cancelled or reaped. Account deletion is two-phase: the API marks the user and removes live data, a Celery task on the new `maintenance` queue deletes the rows. Step 5.9b (data export on MinIO, purge job, monthly audit partitions, column encryption) follows in its own plan.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostGIS, Redis (Lua), Celery (+ beat), pytest (+ Testcontainers, fakeredis, mock Agent in-process).

**Spec:** `docs/02_api_spec.md` §6.2 (E-05), §7.4 (E-20), §4 (scopes) · `docs/03_data_design.md` §3.1, §3.7, §3.9, §4 (reaper query), §5.2, §6.2 · `docs/04_project_structure.md` §6 (queues).

## Global Constraints

- Layer rules of `docs/04_project_structure.md` §2 (+ D-58); `domain` stays framework-free.
- Another user's job → `404`; `/v1/me` only ever touches the caller.
- `prediction_records` has no user id, no exact coordinates (geohash P-48) and no text; written only with `consent_analytics` (D-13).
- Audit rows carry the pseudonym, never `sub` of a normal user, e-mail or IP.
- No token, e-mail, coordinates or free text in logs.
- New numbers go to the Tunable Parameters table; new choices to the Decision Log.
- Git: the user commits; no AI attribution. Commands: `python -m uv run ...`.

## Decisions made while planning

| ID | Decision | Why |
|---|---|---|
| D-72 | `DELETE /v1/jobs/{id}` marks the job and its recommendation `cancelled` in the database at once, publishes the terminal `cancelled` event, frees the active-job slot and answers `202` with the job. No Celery revoke: the worker skips a job that is no longer active when it starts, and while it waits for the Agent it checks the job row every second and cancels the Agent run (`DELETE /runs/{id}`) | revoke needs the broadcast channel and is lost on worker restart; the database check always works |
| D-73 | A result or failure never overwrites a job that is no longer `queued`/`running` (cancelled or reaped): it is discarded (`job_result_discarded`). The Redis job hash never leaves a terminal status (Lua guard) | late workers must not resurrect a cancelled job |
| D-74 | Reaper task `reap_stuck_jobs` (beat every P-60 = 5 min, queue `maintenance`): jobs `queued`/`running` older than P-04 × 2 become `failed` with `AGENT_TIMEOUT`, the failed event is published and the slot freed; at most 100 per run | closes the 5.6 gap of jobs that a worker never loaded |
| D-75 | The worker writes a `prediction_records` row for a successful job when the user has `consent_analytics` at that moment. A pure domain function builds it (geohash P-48, departure rounded down to the hour, lead time in whole hours, hazard types, freshness, service status, rules, versions); region = coverage area of the origin. Cache hits and failures are not recorded | D-13; one copy per Agent answer |
| D-76 | `PATCH /v1/me` is a merge patch: `display_name` (cleaned, ≤ 100, `null` clears), `language` (`th`/`en`), `timezone` (IANA), `home_region` (ISO 3166 `TH` or `TH-50`, `null` clears), `consents.live_alerts` / `consents.analytics` (bool). Turning a consent on stores the server time, off clears it; every consent change writes audit `user.consent` | PDPA evidence of consent |
| D-77 | The user's `live_alerts` consent is the master switch: turning alerts on for a trip also records it; withdrawing it turns alerts off on every trip; the alert scan requires both | one place to withdraw consent |
| D-78 | `DELETE /v1/me` → `202`: sets `deleted_at`, cancels active jobs, deletes the user's live Redis data (active-job and stream sets, job hashes and events, stored idempotent responses), writes audit `user.delete_requested` and queues `delete_account` on `maintenance`. Requests of a user with `deleted_at` get `403 FORBIDDEN` ("account is being deleted"). The reaper re-queues deletions still pending after P-61 = 10 min | the rows go away asynchronously; nothing live survives the request |
| D-79 | `delete_account`: feedback of the user gets `comment = NULL`, `pseudonymous_id = 'deleted'`; then `DELETE FROM users` (cascade); audit `user.delete` (actor `system`, `actor_ref` = pseudonym). Running it twice is harmless | data design §6.2 |
| D-80 | `/v1/me` needs `profile:read` / `profile:write`. `email_masked` comes from the token's `email` claim (`s***@example.com`) and is never stored | DP-04 |

New tunables: P-60 `REAPER_INTERVAL_MINUTES` = 5 · P-61 `ACCOUNT_DELETION_RETRY_MINUTES` = 10.

Deferred to 5.9b: data export (E-21/E-22, MinIO), purge job (P-50), monthly audit partitions, column encryption (D-15).

---

## File Map

| File | Responsibility |
|---|---|
| `app/domain/profile.py` | `ProfileChanges`, `ConsentChanges`, `apply_profile_changes`, `mask_email` |
| `app/domain/prediction.py` | `PredictionData`, `build_prediction` |
| `app/core/config.py` | P-60, P-61 (`MaintenanceSettings`) |
| `app/services/ports.py` | `ProfileRecord`, `UserRepository`, `CancelOutcome`, `JobOutcome.prediction`, `UserRef.deletion_requested`, cancel / reaper methods |
| `app/infrastructure/db/repositories/users.py` | profile, consent side effects on trips, deletion request, account deletion, pending deletions |
| `app/infrastructure/db/repositories/recommendations.py` | `cancel_job`, `job_cancelled`, `reap_stuck_jobs`, finish guard, prediction insert, `deletion_requested` in `get_or_create_user` |
| `app/infrastructure/db/repositories/trips.py` | scan requires user consent; enabling trip alerts records user consent |
| `app/infrastructure/redis/job_state.py`, `app/infrastructure/redis/user_data.py` | terminal guard; forget a user's live data |
| `app/services/job_service.py`, `app/services/agent_run_service.py`, `app/services/reaper_service.py`, `app/services/me_service.py`, `app/services/account_service.py`, `app/services/user_service.py` | use cases |
| `app/schemas/v1/me.py`, `app/api/v1/me.py`, `app/api/v1/jobs.py`, `app/api/deps.py`, `app/api/v1/router.py` | HTTP |
| `app/infrastructure/queue.py`, `app/workers/celery_app.py`, `app/workers/schedule.py`, `app/workers/runtime.py`, `app/workers/tasks/maintenance.py` | queue `maintenance`, tasks, schedule |
| `docker-compose.yml`, `.env.example`, docs, README | wiring and documentation |

---

### Task 1: Profile rules and prediction builder (pure)

**Files:** Create `app/domain/profile.py`, `app/domain/prediction.py`; Test `tests/unit/domain/test_profile.py`, `tests/unit/domain/test_prediction.py`

**Interfaces:**
- `Consents(live_alerts: bool, live_alerts_at: datetime | None, analytics: bool, analytics_at: datetime | None)`
- `Profile(display_name: str | None, language: str, timezone: str, home_region: str | None, consents: Consents)`
- `ConsentChanges(live_alerts: bool | None = None, analytics: bool | None = None)`
- `ProfileChanges(display_name, language, timezone, home_region: str | None = None, consents: ConsentChanges | None = None, explicit_nulls: frozenset[str] = frozenset())`
- `apply_profile_changes(current: Profile, changes: ProfileChanges, *, now: datetime) -> Profile` — `InvalidInput` for: `display_name` > 100 (`too_long`), `language` not `th`/`en` (`unsupported`), unknown `timezone` (`unknown_timezone`), `home_region` not `^[A-Z]{2}(-[A-Z0-9]{1,3})?$` (`invalid`), `null` on `language`/`timezone`/`consents.*` (`required`); blank display name → `None`; consent on → `*_at = now` (unchanged when already on), off → `None`.
- `consent_changes(before: Consents, after: Consents) -> dict[str, bool]` — the consents that changed.
- `mask_email(email: str | None) -> str | None` — `sakda@example.com` → `s***@example.com`; invalid → `None`.
- `PredictionData(origin_geohash, destination_geohash, region_code, departure_bucket, lead_time_hours, travel_modes, status, risk_level, risk_score, risk_confidence, recommendation_type, hazard_types, data_freshness, service_status, safety_gate_rules, agent_version, risk_model_version, prompt_version)`
- `build_prediction(request: NormalizedTravelRequest, result: StoredResultLike, *, now: datetime, region_code: str | None, precision: int) -> PredictionData` where the result fields used are `status`, `risk_level`, `risk_score`, `risk_confidence`, `recommendation_type`, `payload`, `applied_rules` and the version fields (typed with a small Protocol in the domain).

- [x] **Step 1: tests** — every validation above; consent timestamps (on, still on, off); explicit nulls; unchanged input object; `mask_email` cases (normal, one-letter local part, missing `@`, `None`); prediction: geohash length = precision and no coordinates anywhere in the record, departure bucket rounded down to the hour in UTC, lead time floor and never negative, hazard types unique and sorted from the payload, missing payload parts → empty values, rules and versions copied.
- [x] **Step 2–4:** fail → implement → pass (layering test passes).

---

### Task 2: Settings, ports and the user repository

**Files:** Modify `app/core/config.py`, `app/services/ports.py`, `app/infrastructure/db/repositories/recommendations.py` (`get_or_create_user`), `app/infrastructure/db/repositories/trips.py`; Create `app/infrastructure/db/repositories/users.py`; Test `tests/unit/test_config.py`, `tests/integration/test_user_repository.py`, additions to `tests/integration/test_trip_repository.py`

**Interfaces:**
- `MaintenanceSettings(reaper_interval_minutes=5, account_deletion_retry_minutes=10)`; `Settings.maintenance`.
- `UserRef` gains `deletion_requested: bool = False` (last field).
- `ProfileRecord(user_id, profile: Profile, created_at)`
- `UserRepository(Protocol)`:
  - `profile(user_id) -> ProfileRecord | None`
  - `update_profile(user_id, profile: Profile, *, now) -> ProfileRecord | None` — when `live_alerts` goes off, every trip of the user gets `alerts_enabled = false`, `alerts_consent_at = NULL` in the same transaction (D-77)
  - `request_deletion(user_id, *, now) -> bool` (False when already requested)
  - `recent_job_ids(user_id, *, since: datetime) -> list[UUID]`
  - `delete_account(user_id) -> str | None` — anonymizes feedback, deletes the user; returns the pseudonym or `None` when already gone
  - `pending_deletions(*, older_than: datetime, limit: int) -> list[UUID]`
- Trip repository: `create`/`update` with alerts on set `users.consent_live_alerts = true` (+ time if it was off); `due_for_alerts` joins `users` and requires `consent_live_alerts`.

- [x] **Step 1: tests** — config defaults/env; profile round trip; update stores consents and turning live alerts off disables alerts of all the user's trips (not other users'); `request_deletion` once true then false; `get_or_create_user` returns `deletion_requested=True`; `recent_job_ids` only of the user and after `since`; `delete_account` removes user, conversations, trips, recommendations, jobs, keeps and anonymizes feedback, keeps prediction records, returns the pseudonym, second call `None`; `pending_deletions` by age; trip alert on sets user consent; scan skips a trip whose user withdrew consent.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 3: Cancel, finish guard, reaper and prediction insert (repository + Redis)

**Files:** Modify `app/infrastructure/db/repositories/recommendations.py`, `app/infrastructure/redis/job_state.py`; Create `app/infrastructure/redis/user_data.py`; Test additions to `tests/integration/test_recommendation_repository.py`, `tests/unit/test_redis_flow_stores.py`, new `tests/unit/test_redis_user_data.py`

**Interfaces:**
- `CancelOutcome = Literal["cancelled", "not_cancellable"] | None` (None = not found); `RecommendationRepository.cancel_job(user_id, job_id, *, now) -> tuple[CancelOutcome, JobRecord | None]`
- `job_cancelled(job_id) -> bool` (status is no longer active)
- `reap_stuck_jobs(*, older_than: datetime, now: datetime, limit: int) -> list[JobRecord]`
- `finish_job(job_id, outcome) -> bool` — False (and nothing but the agent run row stored) when the job is no longer active
- `JobOutcome.prediction: PredictionData | None = None` — inserted with the result only when the user has `consent_analytics` (`expires_at = now + P-46`, which moves into `JobOutcome.prediction_days: int = 365`)
- Redis: `update()` does nothing once the stored status is terminal (`succeeded`, `failed`, `cancelled`); `RedisUserData(redis, keys).forget(user_id, *, principal_hash: str, job_ids: list[UUID]) -> int` deletes `jobs:active`, `streams`, `job:{id}`, `job:{id}:events` and `idem:{principal_hash}:*` (SCAN, batches of 100).

- [x] **Step 1: tests** — cancel queued/running → both rows `cancelled`, `finished_at` set; cancel finished → `not_cancellable`; other user → `None`; finish after cancel → False, recommendation stays cancelled, no assistant message, agent run row stored; reaper picks only old active jobs and marks them failed with `AGENT_TIMEOUT`, recommendation failed; prediction row written with consent, not without; Redis terminal guard; forget removes exactly the user's keys and leaves another user's.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 4: Job cancel use case and worker watch

**Files:** Modify `app/services/job_service.py`, `app/services/agent_run_service.py`; Test `tests/integration/test_job_cancel.py`, additions to `tests/integration/test_agent_run_service.py`

**Interfaces:**
- `JobService.cancel(user_id, job_id) -> JobRecord` — 404 / `409 JOB_NOT_CANCELLABLE`; publishes `cancelled` (`{"job_id"}`), sets the Redis hash to `cancelled`, releases the slot; Redis errors are logged, not raised (the database decided).
- `AgentRunService`: runs the Agent call as a task next to a watcher that calls `job_cancelled` every `CANCEL_POLL_SECONDS = 1.0`; on cancel it cancels the call (the client sends `DELETE /runs/{id}`), stores the agent run as `cancelled` through `finish_job` and returns `JobStatus.CANCELLED` without publishing; when `finish_job` returns False it skips the cache and the Redis events (`job_result_discarded`). Builds `PredictionData` for successful results (region from `region_for(origin)`).

- [x] **Step 1: tests (mock Agent with `slow` scenario)** — cancel while the Agent runs → job/recommendation cancelled, mock Agent got the cancel for the run id, SSE/stream ends with one `cancelled` event, slot free, no `completed` event; cancel a queued job → worker skips it; cancel twice → 409; other user → 404; a successful job of a user with analytics consent → one prediction record without coordinates.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 5: Reaper and account use cases

**Files:** Create `app/services/reaper_service.py`, `app/services/me_service.py`, `app/services/account_service.py`; Modify `app/services/user_service.py`, `app/infrastructure/queue.py`, `app/services/ports.py` (`JobQueue.enqueue_account_deletion`); Test `tests/integration/test_reaper_service.py`, `tests/integration/test_me_service.py`, `tests/unit/services/test_user_service.py`

**Interfaces:**
- `ReaperService(recommendations, users, job_state, slots, queue, keys, settings, clock).run() -> ReapResult(reaped: int, deletions_requeued: int)` — publishes `failed` with `AGENT_TIMEOUT` for each reaped job, frees slots, re-queues pending deletions older than P-61.
- `MeService(users: UserRepository, recommendations, job_service: JobService, user_data: UserDataPort, audit: AuditPort, queue: JobQueue, settings, clock)`:
  - `get(user, *, email: str | None) -> tuple[ProfileRecord, str | None]`
  - `update(user, changes, *, correlation_id, ip_hash) -> ProfileRecord` (audit `user.consent` with the changed consents)
  - `delete(user, *, principal_hash, correlation_id, ip_hash) -> None` (D-78)
- `AccountService(users, audit, clock).delete(user_id, *, correlation_id) -> bool`
- `UserService.resolve` raises `403 FORBIDDEN` "This account is being deleted." when `deletion_requested`.
- `CeleryJobQueue.enqueue_account_deletion(user_id, *, correlation_id) -> str` (queue `maintenance`, only the id).

- [x] **Step 1: tests** — reaper end to end (stuck job → failed event readable by SSE, slot free; fresh job untouched; pending deletion re-queued); me get/update (consent audit rows with pseudonym; no audit when consents unchanged); delete: jobs cancelled, Redis data gone, audit row, deletion queued once, second call does not queue again; account delete removes rows and writes audit; resolve → 403 after request.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 6: HTTP layer

**Files:** Create `app/schemas/v1/me.py`, `app/api/v1/me.py`; Modify `app/api/v1/jobs.py`, `app/api/deps.py`, `app/api/v1/router.py`, `tests/api/fakes.py`; Test `tests/api/test_me_api.py`, additions to `tests/api/test_jobs_api.py`, `tests/integration/test_me_flow_api.py`

**Contract:**
- `GET /v1/me` (`profile:read`) → `{user_id, display_name, email_masked, language, timezone, home_region, consents: {live_alerts, analytics}, created_at}`
- `PATCH /v1/me` (`profile:write`, merge patch or JSON) → same body; unknown fields → 422
- `DELETE /v1/me` (`profile:write`) → `202 {"status": "deleting"}`
- `DELETE /v1/jobs/{id}` (`travel:write`) → `202` job body; `409 JOB_NOT_CANCELLABLE`; `404`
- A user whose deletion is pending gets `403` on every authenticated endpoint.

- [x] **Step 1: tests** — API with fakes (bodies, scopes, 422, 202/409/404, merge-patch content type, `user_id` is the internal id); integration over HTTP: patch consents → GET shows them; delete → next request 403 → run the deletion task inline → a new login with the same `sub` gets a fresh empty account.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 7: Worker tasks, schedule and compose

**Files:** Create `app/workers/tasks/maintenance.py`; Modify `app/workers/celery_app.py`, `app/workers/schedule.py`, `app/workers/runtime.py`, `docker-compose.yml`, `.env.example`, `Makefile` (if needed); Test `tests/unit/test_workers.py`

**Interfaces:** `MAINTENANCE_QUEUE = "maintenance"`, `REAP_STUCK_JOBS`, `DELETE_ACCOUNT`; beat entry `reap-stuck-jobs` every P-60 (expires = interval); `WorkerRuntime.reap_stuck_jobs() -> dict[str, int]`, `WorkerRuntime.delete_account(user_id) -> bool`; worker command `-Q recommendations,alerts,maintenance`.

- [x] **Step 1: tests** — routes and includes, schedule interval, tasks bind a correlation id, invalid user id ignored.
- [x] **Step 2–4:** fail → implement → pass; `docker compose config` valid.

---

### Task 8: E2E, docs, verification, review

- [x] E2E: cancel a slow job (mock scenario `slow_20s`) → 202, SSE ends with `cancelled`; profile patch; account deletion → 403 → account gone (poll) → new account.
- [x] Docs: spec §2 (P-60, P-61), §6.2, §7.4 details, change log; data design §6.2 notes, change log; structure D-72..D-80, tree, §6 queues, §14 (5.9a done, 5.9b pending), change log; README (status, examples).
- [x] Verification: ruff, mypy, pytest (all), Docker rebuild + E2E, log scan.
- [x] Inline review, fixes, notes; report to the user (they commit).

---

## Self-Review

- Spec coverage: E-05 (Tasks 3, 4, 6), E-20 GET/PATCH/DELETE (1, 2, 5, 6), account deletion §6.2 (2, 5, 7), reaper §4 (3, 5, 7), `prediction_records` §3.9 + D-13 (1, 3, 4), consents (1, 2, 5), beat schedule (7).
- Types: `Profile`, `Consents`, `ProfileChanges`, `ConsentChanges`, `PredictionData`, `ProfileRecord`, `CancelOutcome`, `ReapResult` are defined in Tasks 1–5 and used with the same names later.

## Execution Notes (2026-09-18)

Tasks 1–8 were executed in order, test-first (RED = import error or failing assertion before the code), with these exceptions and differences:

- Task 2: `UserRef.deletion_requested` is filled from `users.deleted_at` by the existing `user_ref()` mapper, so `get_or_create_user` needed no other change.
- Task 3: deleting keys while `SCAN` runs skipped some keys (seen with 255 keys in fakeredis); `RedisUserData.forget` now collects the keys first and deletes them in batches.
- Task 4: the first version cancelled the Agent task but read its result before the task had finished (`InvalidStateError`, found by the integration test). The worker now waits for both the call and the watcher to end, which also lets the client send the cancel to the Agent. `WorkItem.analytics` (from the user row when the job starts) avoids a region lookup for users without consent; the repository checks the consent again when it stores the record.
- Task 5: `MeService` cancels the user's recent jobs through `JobService.cancel`, so the Redis event and slot handling is the same as E-05.
- Task 6: E-05 and `DELETE /v1/me` first returned their own `JSONResponse`, which drops the `RateLimit-*` headers; both now use `json_response`. The header test was added together with that fix, so it was not seen failing first. `UserDataPort` moved to `ports.py` and `AppResources.user_data` holds the Redis implementation, like the other stores. `tests/integration/test_me_flow_api.py` was written after the endpoints existed; it passed on its first run.
- Task 7: the fallback correlation id of `delete_account` is a new id, not the user id.
- Task 8: the E-2E `scenario` fixture moved to `tests/e2e/conftest.py` so every E2E file can use it. A beat run with `REAPER_INTERVAL_MINUTES=1` in the beat container sent `reap-stuck-jobs` and the worker logged `reaper_run`. `job_result_discarded` is no longer logged when the worker only records the agent run of a job the user cancelled.

### Code review (inline)

- Checked: every `/v1/me` call uses the caller's own id; another user's job is `404`; a user being deleted gets `403` everywhere (resolved once per request); audit rows carry the pseudonym and only booleans or report types; `prediction_records` has geohashes and no names, text or user id; deleting an account also removes stored idempotent responses, which may contain request bodies; the reaper and the cancel path free the active-job slot.
- Minor, open: turning alerts on for a trip records the user's `live_alerts` consent (D-77) without an audit row; only `PATCH /v1/me` writes `user.consent`.
- Minor, open: each running job checks the database once a second for cancellation; fine for the current worker concurrency (2), worth revisiting if concurrency grows.
- Minor, open: after the deletion task finishes, the same login gets a new empty account immediately; the Web App should sign the user out after `DELETE /v1/me`.

Final verification: see the step report.
