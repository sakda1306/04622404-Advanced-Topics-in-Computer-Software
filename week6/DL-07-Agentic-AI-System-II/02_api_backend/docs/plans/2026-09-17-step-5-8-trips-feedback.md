# Step 5.8 — Trips, Live Alerts, Feedback and Safety Review Implementation Plan

**Goal:** Users can save trips, re-assess them on demand, receive in-app alerts when a saved trip's risk changes (with consent), and send feedback on a recommendation; unsafe or incorrect advice reports land in a safety review queue that reviewers can work through.

**Architecture:** Same layers as steps 5.6–5.7. A trip assessment is a normal recommendation job (`source = TRIP_ASSESSMENT` / `TRIP_ALERT`, job type `TRIP_ASSESSMENT`) created through `RecommendationService.create`, so the worker, Safety Gate, job state and SSE are reused. Celery beat runs a scan task that queues re-assessments for trips with alerts on. Feedback is stored with the user's pseudonym only; reports that need review are routed to the queue, announced in the log and written to the audit log.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostGIS, Alembic, Redis, Celery (+ beat), pytest (+ Testcontainers, fakeredis, mock Agent in-process).

**Spec:** `docs/02_api_spec.md` §7.2 (E-14..E-18), §7.3 (E-19), §8.2 (review rows), §4 (scopes, limits) · `docs/03_data_design.md` §3.4, §3.10, §3.12, §4 · `docs/04_project_structure.md` §6 (queues).

## Global Constraints

- Layer rules of `docs/04_project_structure.md` §2 (+ D-58); `domain` stays framework-free.
- Another user's trip or recommendation → `404` (never `403`); every repository read filters by `user_id`.
- Feedback rows carry `pseudonymous_id`, never `user_id`; no comment text, coordinates or tokens in logs.
- Comment and review note ≤ 1,000 characters after cleaning; trip name ≤ 100.
- Trip assessments go through the unchanged Safety Gate (never `TRAVEL_NORMALLY` without fresh data).
- Live alerts only when `alerts.enabled = true` and consent was given.
- New numbers go to the Tunable Parameters table (P-55..P-59); new choices to the Decision Log.
- Git: the user commits; no AI attribution. Commands: `python -m uv run ...`.

## Decisions made while planning

| ID | Decision | Why |
|---|---|---|
| D-59 | Trip `departure_time` must not be in the past and at most P-55 (90 days) ahead; P-43 (14 days) applies only when assessing. The window is checked only when `departure_time` is set or changed | trips are planned further ahead than a forecast reaches; an `ACTIVE` trip can still be renamed |
| D-60 | `PATCH /v1/trips/{id}` is JSON Merge Patch (RFC 7396): `origin`, `destination`, `waypoints` are replaced whole; `preferences` and `alerts` are merged per key; `null` on a required field → `422` | matches the spec; locations are values |
| D-61 | Status: `PLANNED → ACTIVE / COMPLETED / CANCELLED`, `ACTIVE → COMPLETED / CANCELLED`. `COMPLETED` and `CANCELLED` trips are closed: any change or assessment → `422` (`status`, `trip_closed`); other moves → `422` (`status`, `invalid_transition`) | simple, predictable lifecycle |
| D-62 | Turning alerts on requires `alerts.consent_at` in the body; the server stores its own clock time as the consent time. Turning alerts off clears it | the stored time must be trustworthy; withdrawal is recorded by clearing |
| D-63 | Trip assessments reuse the conversation of the trip's latest assessment (the first one creates it). `POST .../assessments` body `{mode?, language?}`; language: body → `Accept-Language` → user profile. Job type `TRIP_ASSESSMENT` for sources `TRIP_ASSESSMENT` and `TRIP_ALERT` | one thread per trip instead of one per assessment |
| D-64 | `last_assessment` is the latest finished assessment plus `outdated`. A result is linked only if it is newer than the linked one; `outdated` is cleared only when the result's request matches the trip's current origin, destination, waypoints, departure time and preferences. Failed jobs change nothing | a result for an old route must not look current |
| D-65 | Beat runs `scan_trip_alerts` every P-56 (15 min) on queue `alerts`. It queues async re-assessments (`source = TRIP_ALERT`) for trips with alerts on, status `PLANNED`/`ACTIVE`, departure within P-57 (24 h), whose last assessment is missing, outdated or older than P-58 (60 min), and with no assessment still processing; at most P-59 (100) per scan. A user at P-33 is skipped until the next scan. The `beat` container moves from 5.9 to 5.8 | alerts need a schedule; limits keep Agent load bounded |
| D-66 | The in-app alert is an assistant message in the trip's conversation. For `TRIP_ALERT` results it is stored only when the risk level or recommendation type differs from the previous assessment (log event `trip_alert_raised`, no PII). Push over WebSocket waits for E-07 | no notification table exists; unchanged results would only add noise |
| D-67 | Feedback is accepted only for finished recommendations (`422`, `recommendation_id`, `not_finished`) and must say something (`rating`, `helpful`, `report_type`, `comment` or an `outcome` other than `UNKNOWN`; else `422`, `feedback`, `feedback_empty`). A recommendation may get several feedback rows | a rating of unfinished advice is meaningless; retries are covered by `Idempotency-Key` |
| D-68 | "Notify Ops" for `UNSAFE_ADVICE` / `INCORRECT_INFO` = warning log event `safety_review_requested` (feedback id and report type only) plus audit row `feedback.report`; a metric and alert rule follow in 5.10 | no paging system yet; logs are collected by the monitoring module |
| D-69 | The review queue endpoints (`safety:review`) are built now; the other admin endpoints stay in 5.11. The API uses the stored lowercase values (`pending`, `approved`, `rejected`). Only `pending` feedback can be reviewed, otherwise `409 REVIEW_NOT_PENDING` (new code). `approved` sets `usable_for_training = true`. The queue is ordered oldest first. Listing and reviewing write audit rows | the queue is useless without a way to work it; one vocabulary for status |
| D-70 | `AuditWriter` inserts into `audit_logs` (default partition until 5.9 creates monthly ones). `actor_ref` is the pseudonym for users and the token `sub` for staff; `ip_hash` = HMAC(`IP_HASH_SECRET`, client IP) | data design §3.12 |
| D-71 | Migration `0008` adds `ix_recommendations_trip_recent (trip_id, created_at DESC) WHERE trip_id IS NOT NULL` | E-18, the scan and the conversation lookup filter by trip |

New tunables: P-55 `MAX_TRIP_DAYS_AHEAD` = 90 days · P-56 `TRIP_ALERT_SCAN_MINUTES` = 15 · P-57 `TRIP_ALERT_WINDOW_HOURS` = 24 · P-58 `TRIP_ALERT_REASSESS_MINUTES` = 60 · P-59 `TRIP_ALERT_BATCH_SIZE` = 100.

Deferred: WebSocket push (E-07); `users.consents.live_alerts` (5.9, Me); column encryption of `feedback.comment` (5.9, D-15); monthly audit partitions (5.9); review metrics (5.10); other admin endpoints (5.11); alerts after departure (the assessment rules reject a past departure time).

---

## File Map

| File | Responsibility |
|---|---|
| `app/domain/trips.py` | `TripDraft`, `TripChanges`, `AlertSettings`, status rules, `route_changed`, `apply_trip_changes` |
| `app/domain/feedback.py` | `FeedbackInput`, `review_status_for`, `check_feedback`, `ReviewDecision` |
| `app/domain/normalization.py` (modify) | `check_departure_window` flag |
| `app/domain/enums.py` (modify) | `job_type_for` covers trip sources |
| `app/core/config.py`, `app/core/errors.py` (modify) | P-55..P-59 (`TripSettings`), `REVIEW_NOT_PENDING` |
| `app/services/ports.py` (modify) | trip / feedback / audit records and Protocols |
| `app/infrastructure/db/models/recommendation.py`, `migrations/versions/0008_recommendation_trip_index.py` | D-71 index |
| `app/infrastructure/db/repositories/trips.py` | trips CRUD, assessments list, conversation lookup, due trips |
| `app/infrastructure/db/repositories/feedback.py` | feedback insert, review queue |
| `app/infrastructure/db/repositories/recommendations.py` (modify) | link finished results to trips (D-64, D-66); `feedback_target` |
| `app/infrastructure/audit.py` | `SqlAuditWriter` |
| `app/services/trip_service.py` | create / get / list / update / delete / assess / assessments |
| `app/services/trip_alert_service.py` | `scan(now)` |
| `app/services/feedback_service.py` | `submit`, `reviews`, `review` |
| `app/schemas/v1/trips.py`, `app/schemas/v1/feedback.py` | contracts |
| `app/api/v1/trips.py`, `app/api/v1/feedback.py`, `app/api/v1/admin/reviews.py`, `app/api/v1/router.py`, `app/api/deps.py`, `app/api/audit.py` | HTTP |
| `app/workers/celery_app.py`, `app/workers/runtime.py`, `app/workers/tasks/trip_alerts.py`, `app/workers/schedule.py`, `app/infrastructure/queue.py` | alert scan task, beat schedule |
| `docker-compose.yml`, `Makefile`, `.env.example` | beat service, worker queues |
| `tests/...` | per task; `tests/e2e` gets trip and feedback cases |
| docs, README | decisions, tunables, status |

---

### Task 1: Trip rules (pure)

**Files:** Create `app/domain/trips.py`; Modify `app/domain/normalization.py`, `app/domain/enums.py`; Test `tests/unit/domain/test_trips.py`, additions to `tests/unit/domain/test_normalization.py`

**Interfaces:**
- `normalize_travel_request(raw, *, now, limits, check_departure_window: bool = True)` — when `False`, `in_past` / `too_far_ahead` are not reported (timezone offset is still required).
- `AlertSettings(enabled: bool = False, consent_at: datetime | None = None, channels: tuple[AlertChannel, ...] = (AlertChannel.IN_APP,))`
- `TripDraft(name: str, origin: GeoPoint, destination: GeoPoint, departure_time: datetime, timezone: str, waypoints: tuple[GeoPoint, ...] = (), preferences: TravelPreferences = TravelPreferences(), alerts: AlertSettings = AlertSettings(), status: TripStatus = TripStatus.PLANNED)`
- `PreferenceOverrides` (from `follow_up.py`) is reused for preference changes.
- `AlertChanges(enabled: bool | None = None, consent_at: datetime | None = None, channels: tuple[AlertChannel, ...] | None = None)`
- `TripChanges(name, origin, destination, waypoints, departure_time, timezone, preferences: PreferenceOverrides | None, alerts: AlertChanges | None, status: TripStatus | None)` — all default `None` = keep; `explicit_nulls: frozenset[str] = frozenset()` names the fields the client set to `null`.
- `validate_trip(draft: TripDraft, *, now, limits: NormalizationLimits, check_departure_window: bool) -> TripDraft` — cleans the name (required, ≤ 100), normalizes the route through `normalize_travel_request`, checks channels (non-empty, unique) → `InvalidInput`.
- `apply_trip_changes(current: TripDraft, changes: TripChanges, *, now, limits) -> TripDraft` — raises `InvalidInput` for: `null` on `name`/`origin`/`destination`/`departure_time`/`timezone`/`alerts.enabled`/`status` (`required`), closed trip (`status`, `trip_closed`), bad move (`status`, `invalid_transition`), alerts turned on without `consent_at` (`alerts.consent_at`, `required`); consent time = `now` when alerts turn on, `None` when they turn off, unchanged otherwise.
- `route_changed(before: TripDraft, after: TripDraft) -> bool` — origin, destination, waypoints, departure time or preferences differ.
- `is_closed(status) -> bool`; `job_type_for(TRIP_ASSESSMENT | TRIP_ALERT) -> JobType.TRIP_ASSESSMENT`.

- [x] **Step 1: tests** — validate: name blank → `name/required`, 101 chars → `name/too_long`, departure past or > 90 days → issues, window skipped when asked, duplicate channels → `alerts.channels/duplicate`, empty channels → `alerts.channels/required`, alerts on without consent → `alerts.consent_at/required`, consent stored as `now`; apply: rename keeps route and `route_changed` is false; new departure → window checked, `route_changed` true; preferences merged per key; `waypoints=()` clears; `null` name → `required`; each allowed and each rejected status move; closed trip rename → `trip_closed`; alerts off clears consent; alerts already on and unchanged keeps the old consent time; the input object is unchanged. Normalization: `check_departure_window=False` accepts a past time; `job_type_for` covers all four sources.
- [x] **Step 2: run → import error / failures.**
- [x] **Step 3: implement** (the layering test must still pass).
- [x] **Step 4: run → pass.**

---

### Task 2: Settings, error code, index, trip repository

**Files:** Modify `app/core/config.py`, `app/core/errors.py`, `app/services/ports.py`, `app/infrastructure/db/models/recommendation.py`; Create `migrations/versions/0008_recommendation_trip_index.py`, `app/infrastructure/db/repositories/trips.py`; Test `tests/unit/test_config.py`, `tests/unit/test_errors.py`, `tests/integration/test_trip_repository.py`, `tests/integration/test_migrations.py` (head is `0008`)

**Interfaces:**
- `TripSettings`: `max_trip_days_ahead=90`, `trip_alert_scan_minutes=15`, `trip_alert_window_hours=24`, `trip_alert_reassess_minutes=60`, `trip_alert_batch_size=100`; `Settings.trips`.
- `ErrorCode.REVIEW_NOT_PENDING` → `409 "Review not pending" / "This feedback has already been reviewed."`
- `AssessmentSummary(recommendation_id, status, risk_level, recommendation_type, created_at)`
- `TripRecord(id, user_id, draft: TripDraft, last_assessment: AssessmentSummary | None, assessment_outdated: bool, created_at, updated_at)`
- `DueTrip(trip_id: UUID, user_id: UUID)`
- `TripRepository(Protocol)`:
  - `create(user_id, draft, *, now, retention_days) -> TripRecord`
  - `get(user_id, trip_id) -> TripRecord | None`
  - `list_trips(user_id, *, limit, cursor, status: TripStatus | None) -> list[TripRecord]` (order `departure_time DESC, id DESC`, `limit + 1` rows)
  - `update(user_id, trip_id, draft, *, outdated: bool, now, retention_days) -> TripRecord | None` (`outdated=True` sets the flag, `False` keeps it)
  - `delete(user_id, trip_id) -> bool`
  - `assessments(user_id, trip_id, *, limit, cursor) -> list[RecommendationSummaryRecord] | None`
  - `conversation_for(user_id, trip_id) -> UUID | None` (latest assessment with a conversation)
  - `due_for_alerts(now, *, window, stale_after, processing_after, limit) -> list[DueTrip]`
  - `user(user_id) -> UserRef | None`
- `expires_at = departure_time + P-47` on create and update.

- [x] **Step 1: tests** — config defaults and env names; error spec; migration head and drift test pass with the new index; repository: create/get round trip (points, waypoints, preferences, alerts, channels), other user → `None`; list order, pages, status filter; update changes columns, `expires_at` and `updated_at`, sets `outdated` only when asked, other user → `None`; delete (true once; recommendations keep `trip_id NULL`); assessments of the trip only, newest first, `None` for another user; `conversation_for`; `due_for_alerts` picks only: alerts on, `PLANNED`/`ACTIVE`, departure within the window, last assessment missing / outdated / older than `stale_after`, no processing assessment newer than `processing_after`; respects `limit`, oldest departure first.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 3: Results link back to the trip

**Files:** Modify `app/infrastructure/db/repositories/recommendations.py`; Test additions to `tests/integration/test_recommendation_repository.py`

**Rules (D-64, D-66):** in `finish_job` (success) and `create_completed`, when the recommendation has a `trip_id` and the trip still exists (locked `FOR UPDATE`):
- skip when the linked recommendation is newer;
- remember the previous risk level and type, then set `last_recommendation_id`;
- set `assessment_outdated = False` only when the request matches the trip (`ST_Equals` on origin and destination, equal `departure_time`, `waypoints` and `preferences` JSON); otherwise leave it;
- for `source = TRIP_ALERT`: store the assistant message only when there was a previous assessment and the risk level or type changed (then log `trip_alert_raised` with trip id and levels), otherwise no message; other sources keep D-55.

- [x] **Step 1: tests** — finished trip assessment links the trip and clears `outdated`; a result for an old route links but keeps `outdated`; an older result does not replace a newer link; failed job changes nothing; alert with unchanged risk → no new message; alert with changed risk → assistant message; first alert (no previous) → no message; deleted trip → result still stored.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 4: Trip service and alert scan

**Files:** Create `app/services/trip_service.py`, `app/services/trip_alert_service.py`; Test `tests/integration/test_trip_service.py`, `tests/integration/test_trip_alert_service.py`

**Interfaces:**
- `TripService(trips: TripRepository, recommendations: RecommendationService, settings, clock)`:
  - `create(user, draft) -> TripRecord`; `get(user, trip_id)`; `list(user, *, limit, cursor, status) -> Page[TripRecord]`; `update(user, trip_id, changes) -> TripRecord`; `delete(user, trip_id)`; all 404 when missing.
  - `assess(user, trip_id, *, mode: RequestMode, language: str | None, accept_language: str | None, correlation_id, source: RequestSource = TRIP_ASSESSMENT) -> CreateOutcome` — closed trip → `trip_closed`; builds `TravelRequestInput` from the trip (no question), `conversation_id = conversation_for(...)`, `trip_id` set; language fallback to `user.language`.
  - `assessments(user, trip_id, *, limit, cursor) -> Page[RecommendationSummaryRecord]`.
- `TripAlertService(trips: TripRepository, trip_service: TripService, settings, clock)`: `scan() -> ScanResult(queued: int, skipped: int)` — for each due trip loads the user, calls `assess(..., mode=ASYNC, source=TRIP_ALERT)`; `AppError` (e.g. `TOO_MANY_ACTIVE_JOBS`, `UNSUPPORTED_REGION`) and `InvalidInput` are logged (`trip_alert_skipped`, trip id + code) and counted; other errors propagate.

- [x] **Step 1: tests (inline worker + mock Agent)** — create/update/list/delete via the service; update of the route marks the assessment outdated; assess returns a result with `trip_id`, the trip shows `last_assessment` and `outdated = False`; second assessment reuses the conversation; assessing a trip > 14 days ahead → `departure_time/too_far_ahead`; closed trip → `trip_closed`; other user → 404; language from the user profile; scan queues only due trips, marks them with `source = TRIP_ALERT` and job type `TRIP_ASSESSMENT`, a second scan right after queues nothing (processing / fresh), a user at P-33 is skipped and counted.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 5: Trip HTTP layer

**Files:** Create `app/schemas/v1/trips.py`, `app/api/v1/trips.py`; Modify `app/api/v1/router.py`, `app/api/deps.py`; Test `tests/api/test_trips_api.py` (fake service), `tests/integration/test_trip_flow_api.py`

**Contract:**
- `POST /v1/trips` (`travel:write`, idempotent) body `TripCreate` → `201 Trip` + `Location`.
- `GET /v1/trips?limit&cursor&status` (`travel:read`) → `{items: Trip[], next_cursor}`.
- `GET /v1/trips/{id}` → `Trip`; `PATCH` (`travel:write`, `application/merge-patch+json` or JSON) → `Trip`; `DELETE` (`travel:write`) → `204`.
- `POST /v1/trips/{id}/assessments` (`travel:write`, idempotent, P-32) body `{mode?: auto|sync|async, language?}` → `200 RecommendationResponse` / `202 JobAccepted`.
- `GET /v1/trips/{id}/assessments?limit&cursor` → `{items: RecommendationSummary[], next_cursor}`.
- `Trip` = `trip_id, name, origin, destination, waypoints, departure_time, timezone, preferences, alerts{enabled, consent_at, channels}, status, last_assessment{recommendation_id, status, risk_level, recommendation_type, created_at, outdated} | null, created_at, updated_at`.
- `TripPatch` parses the raw body, so `null` and "missing" differ (`model_fields_set`); unknown fields → 422.

- [x] **Step 1: tests** — API with fakes: status codes, `Location`, scopes (read token cannot write), idempotent replay of POSTs, 422 for unknown fields / naive time / bad status value, merge-patch content type accepted, `null` name → 422 from the domain, 204 empty body. Integration over HTTP: create trip → assess (200) → trip shows `last_assessment` → PATCH departure → `outdated: true` → assessments list → delete → 404; another user → 404 everywhere.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 6: Alert scan task, beat and worker queues

**Files:** Create `app/workers/tasks/trip_alerts.py`, `app/workers/schedule.py`; Modify `app/workers/celery_app.py` (queue `alerts`, route, include, `beat_schedule`), `app/workers/runtime.py` (build `TripAlertService` with a `CeleryJobQueue`), `docker-compose.yml` (worker `-Q recommendations,alerts`, new `beat` service), `Makefile`, `.env.example`; Test `tests/unit/test_workers.py` additions

**Interfaces:**
- `SCAN_TRIP_ALERTS = "app.workers.tasks.trip_alerts.scan_trip_alerts"`, `ALERT_QUEUE = "alerts"`.
- `beat_schedule(settings) -> dict` — one entry every P-56 minutes, routed to `alerts`, `expires` = interval (a missed run is dropped).
- `WorkerRuntime.scan_trip_alerts() -> dict[str, int]`.
- Beat uses a schedule file under `/tmp` (container has no writable app dir).

- [x] **Step 1: tests** — Celery app routes the task to `alerts`, includes the module, schedule interval follows the setting; task binds a correlation id, calls the runtime and returns counts; runtime builds the alert service once per process.
- [x] **Step 2–4:** fail → implement → pass.
- [x] **Step 5:** `docker compose config` is valid; beat and worker start healthy.

---

### Task 7: Feedback and review queue

**Files:** Create `app/domain/feedback.py`, `app/infrastructure/db/repositories/feedback.py`, `app/infrastructure/audit.py`, `app/services/feedback_service.py`, `app/schemas/v1/feedback.py`, `app/api/v1/feedback.py`, `app/api/v1/admin/__init__.py`, `app/api/v1/admin/reviews.py`, `app/api/audit.py`; Modify `app/services/ports.py`, `app/infrastructure/db/repositories/recommendations.py` (`feedback_target`), `app/api/v1/router.py`, `app/api/deps.py`; Test `tests/unit/domain/test_feedback.py`, `tests/integration/test_feedback_repository.py`, `tests/integration/test_feedback_service.py`, `tests/api/test_feedback_api.py`, `tests/api/test_reviews_api.py`

**Interfaces:**
- Domain: `FeedbackInput(rating: int | None, helpful: bool | None, outcome: FeedbackOutcome, report_type: ReportType | None, comment: str | None)`; `check_feedback(raw) -> FeedbackInput` (cleans comment, blank → `None`, > 1,000 → `comment/too_long`, rating outside 1–5 → `rating/out_of_range`, nothing said → `feedback/feedback_empty`); `review_status_for(report_type) -> ReviewStatus` (`pending` for `UNSAFE_ADVICE`/`INCORRECT_INFO`, else `not_required`); `ReviewDecision` = `approved | rejected`.
- Ports: `FeedbackRecord(id, recommendation_id, rating, helpful, outcome, report_type, comment, review_status, reviewed_at, review_note, created_at)`; `ReviewItem(feedback: FeedbackRecord, recommendation: dict | None)` (sanitized payload if the recommendation still exists); `FeedbackRepository`: `create(...) -> FeedbackRecord`, `reviews(*, status, limit, cursor) -> list[ReviewItem]` (oldest first), `review(feedback_id, *, decision, note, reviewer, now) -> FeedbackRecord | None | Literal["not_pending"]`; `RecommendationRepository.feedback_target(user_id, recommendation_id) -> RecommendationStatus | None`; `AuditEntry(actor_type, actor_ref, action, target_type, target_id, result, correlation_id, ip_hash, metadata)`, `AuditPort.write(entry)`.
- `FeedbackService(feedback, recommendations: RecommendationRepository, audit: AuditPort, settings, clock)`: `submit(user, recommendation_id, raw, *, correlation_id, ip_hash) -> FeedbackRecord`; `reviews(reviewer: str, *, status, limit, cursor, correlation_id, ip_hash) -> Page[ReviewItem]`; `review(reviewer, feedback_id, *, decision, note, correlation_id, ip_hash) -> FeedbackRecord` (404 / 409 `REVIEW_NOT_PENDING`).
- HTTP: `POST /v1/recommendations/{id}/feedback` (`travel:write`, idempotent) → `201 {feedback_id, created_at, review_status}`; `GET /v1/admin/feedback/reviews?status=pending&limit&cursor` (`safety:review`) → `{items: [{feedback_id, recommendation_id, rating, helpful, outcome, report_type, comment, review_status, review_note, reviewed_at, created_at, recommendation}], next_cursor}`; `PATCH /v1/admin/feedback/reviews/{feedback_id}` (`safety:review`) body `{status: approved|rejected, note?}` → the item without `recommendation`.
- `client_ip_hash(request) -> str` in `app/api/audit.py`.

- [x] **Step 1: tests** — domain rules; repository: insert with pseudonym and `expires_at = created_at + P-23`, queue order and status filter and pages, review sets reviewer/time/note/`usable_for_training` only for approved, second review → `"not_pending"`, unknown id → `None`; service: other user's or unknown recommendation → 404, processing → `not_finished`, unsafe report → `pending` + audit row `feedback.report` + log `safety_review_requested` without comment text, plain rating → `not_required` and no audit row, review writes audit `feedback.review`, list writes audit `feedback.review_list`; API with fakes: scopes (`travel:write` cannot list reviews; `safety:review` can), 201 body, 409 body, 422 for bad enum / unknown field, idempotent replay.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 8: E2E, docs, verification, review

- [x] E2E against the compose stack: create trip → assess → PATCH → assessments list; feedback with `UNSAFE_ADVICE` → reviewer token lists and approves it; the scan task queued by beat (or triggered with `celery call`) re-assesses a trip with alerts on.
- [x] Docs: spec §2 (P-55..P-59), §3 (`REVIEW_NOT_PENDING`), §7.2 / §7.3 / §8.2 details, §14, change log 0.9; data design (index `0008`, change log 0.5); structure (tree, §5 beat, §6 queues, D-59..D-71, §14 status, change log 0.9); README status, trips and feedback examples.
- [x] Verification: ruff format/check, mypy, pytest (all), Docker rebuild + E2E, log scan (no comment text, coordinates or tokens).
- [x] Inline review, fixes, notes below; report to the user (they commit).

---

## Self-Review

- Spec coverage: E-14 (Tasks 1, 2, 4, 5), E-15 (2, 4, 5), E-16 GET/PATCH/DELETE (1, 2, 4, 5), E-17 (1, 3, 4, 5), E-18 (2, 4, 5), live alert with consent (1, 3, 4, 6), E-19 (7), review queue + "notify Ops" (7), retention P-23 / P-47 (2, 7), audit on admin actions (7).
- Types: `TripDraft`, `TripChanges`, `AlertSettings`, `AlertChanges`, `TripRecord`, `AssessmentSummary`, `DueTrip`, `FeedbackInput`, `FeedbackRecord`, `ReviewItem`, `AuditEntry` are defined in Tasks 1, 2 and 7 and used with the same names later.

## Execution Notes (2026-09-17)

Tasks 1–8 were executed in order, test-first. Differences from the plan:

- Task 1: `validate_trip` and `apply_trip_changes` first stopped at a missing consent before the other checks. The HTTP integration test showed that `timezone` errors were then hidden, so all problems are now collected and reported together (a unit test failed first). `_preferences` builds the new value without `type: ignore`.
- Task 2: the repository tests were written before the repository but were not run to see them fail first; the first run was after the code existed. From Task 3 on every RED run was done. `summary_record()` and `user_ref()` became public in the recommendation repository so the trip repository reuses them; the request preferences parser became `parse_preferences()`. One test helper passed `departure_time` twice (test bug, fixed).
- Task 3: `_same_route` first produced an SQLAlchemy cartesian-product warning; it now joins the request explicitly.
- Task 5: `TripPatch` needs no `Body()`; FastAPI already parses `application/merge-patch+json`, and the OpenAPI document lists both media types.
- Task 6: `WorkerRuntime` got one `_call()` helper for both tasks. The compose `beat` block was first inserted inside `worker.depends_on` (the marker `migrate:` matched there); `docker compose config` caught it.
- Task 7: `ReviewDecision.status` maps the decision to the stored `ReviewStatus`. The audit rows in the service test are ordered by id.
- Task 8: a beat run with `TRIP_ALERT_SCAN_MINUTES=1` inside the beat container sent `scan-trip-alerts`, and the worker logged `trip_alert_scan`. The README examples were run against Docker. `curl.exe` on Windows turns Thai text in `-d '...'` into `?` before sending (the API stores what it receives; Python clients and `--data-binary @file` keep UTF-8), so the README now says so. Files edited with Python on this machine were written with CRLF; the changed code files were converted to LF, the line ending in `.gitattributes` (Git stores LF either way, so the diff shows only real changes).

### Code review (inline)

- Fixed during review: the worker unit test imported `tests.integration.flow` only for `tune()`; it now copies the settings itself.
- Checked: every user-facing trip and feedback query filters by `user_id`; the alert scan only reads trips with alerts on and consent; logs carry ids, risk levels and report types but no comment text, coordinates or tokens (log scan: 0 hits); reviewers need `safety:review`; `approved` is the only way to `usable_for_training`; the PATCH OpenAPI entry lists both media types.
- Minor, open: the first scheduled re-assessment of a trip that was never assessed creates a conversation without messages (the alert message is only written when the risk changes).
- Minor, open: a review is committed before its audit row is written; if the audit insert fails, the client gets `500` and a retry gets `409`.
- Minor, open: if a trip's conversation is deleted between the lookup and the new assessment, that one request returns `404` (the next one starts a new conversation).
- Deferred as planned: WebSocket push, `users.consents.live_alerts`, `feedback.comment` encryption, monthly audit partitions, review metrics.

Final verification: see the step report.
