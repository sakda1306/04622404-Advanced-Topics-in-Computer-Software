# Step 5.7 — Conversations, Follow-up and History Implementation Plan

**Goal:** Users can keep a conversation with the assistant: create and list conversations, read messages, ask follow-up questions that re-assess the last request with changes (`overrides`), delete a conversation, and browse their recommendation history.

**Architecture:** Same layers as step 5.6. A follow-up message becomes a normal recommendation job (`source = MESSAGE`, job type `MESSAGE`) through `RecommendationService.create`, so the worker, Safety Gate, job state and SSE are reused unchanged. The base request is the conversation's last travel request; a pure domain function merges the overrides into it and normalization runs again. Lists use keyset pagination with an opaque base64url cursor.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostGIS, Redis, pytest (+ Testcontainers, fakeredis, mock Agent in-process).

**Spec:** `docs/02_api_spec.md` §1 (pagination), §5.5 (E-02), §7.1 (E-08..E-13) · `docs/03_data_design.md` §3.2, §3.3, §4 (query patterns, cursor format).

## Global Constraints

- Layer rules of `docs/04_project_structure.md` §2; `domain` stays framework-free.
- Page size default 20, max P-40 = 50; cursor = base64url of `{"t": <timestamp>, "id": <uuid>}`, validated.
- Message content ≤ P-41 (1,000 characters) after cleaning; conversation title ≤ 200 characters.
- Context sent to the Agent: last P-45 = 10 messages.
- Another user's conversation or recommendation → `404` (never `403`).
- Every follow-up re-assesses (never served from the cache).
- Never answer `TRAVEL_NORMALLY` without fresh weather/disaster data (unchanged Safety Gate).
- Git: the user commits; no AI attribution. Commands: `python -m uv run ...`.

## Decisions made while planning

| ID | Decision | Why |
|---|---|---|
| D-52 | `POST .../messages` with `stream=true` always answers `202` (like `mode=async`); `stream=false` behaves like `mode=auto` | the client asked to follow `events_url` |
| D-53 | Follow-up jobs use `jobs.type = MESSAGE` and `travel_requests.source = MESSAGE`; the worker treats them like recommendation jobs | the spec lists `MESSAGE` as a job type; one worker path |
| D-54 | Overrides replace whole fields, except `preferences`, which is merged per key; `waypoints: []` clears them. A conversation without an earlier request needs `origin`, `destination`, `departure_time` and `timezone` in `overrides`, otherwise `422` (`overrides`, `travel_context_required`) | a partial update must be predictable |
| D-55 | The `200` answer of a follow-up is the assistant `Message`; every finished job stores one (a fixed "not enough data" text when the Agent gave neither a summary nor a question) | the spec says `200 Message`; a finished job never leaves the user without a reply |
| D-56 | An invalid cursor or `limit` outside 1–P-40 → `422 VALIDATION_ERROR` with the field name | same shape as other input errors |
| D-57 | Conversation lists are ordered by `updated_at DESC, id DESC` (index `ix_conversations_user_recent`); a conversation that changes while paging may move | uses the existing index; acceptable for a chat list |
| D-58 | `infrastructure` may import `app.services.ports` and `app.services.pagination` (the records and Protocols it implements) | added during execution: step 5.6 already did this; now written down in 04 §2 |

---

## File Map

| File | Responsibility |
|---|---|
| `app/services/pagination.py` | `Cursor`, `Page`, `encode_cursor`, `decode_cursor`, `page_limit` |
| `app/domain/follow_up.py` | `RequestOverrides`, `PreferenceOverrides`, `merge_overrides` |
| `app/services/ports.py` (modify) | conversation / message / summary records, `ConversationRepository` |
| `app/infrastructure/db/repositories/conversations.py` | SQL for conversations and messages |
| `app/infrastructure/db/repositories/recommendations.py` (modify) | `list_recommendations`, job type from source, shared request loader |
| `app/services/recommendation_payload.py` (modify) | fallback assistant text |
| `app/services/recommendation_service.py` (modify) | `source` on the command, `list` |
| `app/services/conversation_service.py` | create / get / list / delete / messages / post_message |
| `app/schemas/v1/conversations.py`, `app/schemas/v1/common.py`, `app/schemas/v1/travel.py` (modify) | contracts |
| `app/api/v1/conversations.py`, `app/api/v1/recommendations.py` (modify), `app/api/v1/router.py`, `app/api/deps.py` (modify) | HTTP |
| `tests/...` | per task; `tests/e2e` gets a follow-up case |
| docs, README | decisions and status |

---

### Task 1: Cursor pagination

**Files:** Create `app/services/pagination.py`; Test `tests/unit/services/test_pagination.py`

**Interfaces:**
- `Cursor(at: datetime, id: UUID)` (frozen), `Page[T](items: list[T], next_cursor: str | None)`
- `encode_cursor(cursor: Cursor) -> str`, `decode_cursor(raw: str | None) -> Cursor | None` (raises `AppError(VALIDATION_ERROR, errors=[FieldError("cursor", ...)])`)
- `page_limit(limit: int | None, *, maximum: int, default: int = 20) -> int` (raises the same error with field `limit`)
- `build_page(rows: list[T], limit: int, key: Callable[[T], Cursor]) -> Page[T]` (rows fetched with `limit + 1`)

- [x] **Step 1: tests** — round trip keeps microseconds and timezone (UTC); output is URL-safe without padding; `None`/empty → `None`; garbage, bad base64, JSON without `t`/`id`, naive timestamp, non-UUID id, over-long input (> 200 chars) → 422 with field `cursor`; `page_limit(None)` = 20, `0`/`51` → 422 field `limit`, `50` ok; `build_page` with `limit + 1` rows returns `limit` items and the cursor of the last item, with ≤ `limit` rows returns `next_cursor None`.
- [x] **Step 2: run → import error.**
- [x] **Step 3: implement.**
- [x] **Step 4: run → pass.**

---

### Task 2: Merge follow-up overrides (pure)

**Files:** Create `app/domain/follow_up.py`; Test `tests/unit/domain/test_follow_up.py`

**Interfaces:**
- `PreferenceOverrides(travel_modes: tuple[TravelMode, ...] | None = None, avoid: ... | None = None, max_travel_hours: int | None = None, mobility_needs: ... | None = None, traveler_count: int | None = None)`
- `RequestOverrides(origin: GeoPoint | None = None, destination: GeoPoint | None = None, waypoints: tuple[GeoPoint, ...] | None = None, departure_time: datetime | None = None, timezone: str | None = None, language: str | None = None, preferences: PreferenceOverrides | None = None)`; `None` = keep the base value
- `merge_overrides(base: NormalizedTravelRequest | None, overrides: RequestOverrides, *, question: str | None, accept_language: str | None, default_language: str) -> TravelRequestInput` — raises `InvalidInput([FieldIssue("overrides", "travel_context_required", ...)])` when `base is None` and a required field is missing

- [x] **Step 1: tests** — only `departure_time` given → everything else from the base, question replaced; preferences merged per key (`avoid` changed, `travel_modes` kept); `waypoints=()` clears; language: override > base; no base + complete overrides → input with `default_language` when no language given; no base + missing `origin`/`timezone` → `InvalidInput` listing the missing fields in the message; the base object is not changed.
- [x] **Step 2–4:** fail → implement → pass (also passes `tests/unit/domain/test_layering.py`).

---

### Task 3: Repository support

**Files:** Create `app/infrastructure/db/repositories/conversations.py`; Modify `recommendations.py`, `app/services/ports.py`, `app/services/recommendation_payload.py`; Test `tests/integration/test_conversation_repository.py`, additions to `tests/integration/test_recommendation_repository.py`, `tests/unit/services/test_recommendation_payload.py`

**Interfaces (ports):**
- `ConversationRecord(id, user_id, title, language, created_at, updated_at, last_recommendation_id, message_count)`
- `MessageRecord(id, conversation_id, role: MessageRole, content, recommendation_id, created_at)`
- `RecommendationSummaryRecord(id, created_at, status, risk_level, recommendation_type, origin_name, destination_name, departure_time)`
- `ConversationRepository(Protocol)`: `create(user_id, *, title, language, now, retention_days) -> ConversationRecord`, `get(user_id, conversation_id) -> ConversationRecord | None`, `list(user_id, *, limit, cursor) -> list[ConversationRecord]` (limit + 1 rows), `delete(user_id, conversation_id) -> bool`, `messages(user_id, conversation_id, *, limit, cursor) -> list[MessageRecord] | None` (`None` = not owned), `last_request(user_id, conversation_id) -> NormalizedTravelRequest | None`, `reply_for(user_id, recommendation_id) -> MessageRecord | None` (assistant message)
- `RecommendationRepository.list_recommendations(user_id, *, limit, cursor, created_from, created_to, risk_level) -> list[RecommendationSummaryRecord]`
- `StoredResult.from_assessment(..., language)` uses `fallback_reply(language)` when there is neither summary nor clarification.

**Rules:** the request loader used by `start_job` moves to a shared helper so `last_request` returns the same `NormalizedTravelRequest` (question = `None`); `create_pending`/`create_completed` set `jobs.type` from `new.source` (`MESSAGE` → `MESSAGE`, otherwise `RECOMMENDATION`); delete relies on the FKs (messages cascade, requests and recommendations `SET NULL`).

- [x] **Step 1: tests** — create/get/list (newest `updated_at` first, keyset pages without overlap, other user sees nothing), delete (true once, false for another user and afterwards; recommendation survives with `conversation_id NULL`; messages gone), messages (newest first, pages, `None` for another user), `last_request` (the latest request, `None` without requests or for another user), `reply_for` (assistant message of a finished recommendation; `None` for another user), job type `MESSAGE` for `source=MESSAGE`, `list_recommendations` (order, pages, `created_from`/`created_to`, `risk_level`, owner only), fallback reply for a partial result without recommendation text.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 4: Services

**Files:** Create `app/services/conversation_service.py`; Modify `app/services/recommendation_service.py`; Test `tests/integration/test_conversation_service.py`, additions to `tests/integration/test_recommendation_service.py`

**Interfaces:**
- `CreateRecommendation` gains `source: RequestSource = RequestSource.RECOMMENDATION`; the job snapshot type follows it.
- `RecommendationService.list(user, *, limit: int | None, cursor: str | None, created_from, created_to, risk_level) -> Page[RecommendationSummaryRecord]`
- `ConversationService(conversations: ConversationRepository, recommendations: RecommendationService, settings, clock)`:
  - `create(user, *, title: str | None, language: str | None, accept_language: str | None) -> ConversationRecord` (title cleaned, ≤ 200, blank → `None`)
  - `get(user, conversation_id)`, `list(user, *, limit, cursor) -> Page[ConversationRecord]`, `delete(user, conversation_id) -> None` (404 when missing)
  - `messages(user, conversation_id, *, limit, cursor) -> Page[MessageRecord]`
  - `post_message(user, conversation_id, *, content: str, overrides: RequestOverrides, stream: bool, accept_language, correlation_id) -> MessageReply | Accepted`, where `MessageReply(message: MessageRecord)`; content cleaned and required (blank → 422 `content`), length checked by normalization (`question`); `stream` → `RequestMode.ASYNC`, else `AUTO`.

- [x] **Step 1: tests (integration with inline worker + mock Agent)** — first question in a new conversation with complete overrides → `MessageReply` with assistant text and `recommendation_id`; follow-up with only `departure_time` → the Agent receives the base origin/destination, the new time, the new question and the earlier messages as context, and the job type is `MESSAGE`; `stream=True` → `Accepted`; empty conversation without overrides → `InvalidInput` (`overrides`); blank content → 422 `content`; another user's conversation → 404 for get/messages/post/delete; delete then get → 404 and the recommendation is still readable by its owner; list pages; `RecommendationService.list` filters and pages; follow-up never uses the cache.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 5: HTTP layer

**Files:** Create `app/schemas/v1/common.py` (`PageResponse` helper), `app/schemas/v1/conversations.py`, `app/api/v1/conversations.py`; Modify `app/schemas/v1/travel.py` (`RecommendationSummary`, `TravelOverrides`), `app/api/v1/recommendations.py` (list), `app/api/v1/router.py`, `app/api/deps.py`; Test `tests/api/test_conversations_api.py`, additions to `tests/api/test_recommendations_api.py`, `tests/integration/test_conversation_flow_api.py`

**Contract:**
- `POST /v1/conversations` (`travel:write`, idempotent, P-32) body `{title?, language?}` → `201 Conversation` + `Location`
- `GET /v1/conversations?limit&cursor` (`travel:read`) → `{items: Conversation[], next_cursor}`
- `GET /v1/conversations/{id}` → `Conversation`; `DELETE` (`travel:write`) → `204`
- `GET /v1/conversations/{id}/messages?limit&cursor` → `{items: Message[], next_cursor}`
- `POST /v1/conversations/{id}/messages` (`travel:write`, idempotent, P-32) body `{content, overrides?, stream=false}` → `200 Message` or `202 JobAccepted` + `Location`
- `GET /v1/travel/recommendations?limit&cursor&from&to&risk_level` (`travel:read`) → `{items: RecommendationSummary[], next_cursor}`; `from`/`to` must include a timezone.
- `TravelOverrides` (`extra="forbid"`, all optional, `preferences` partial) maps to `RequestOverrides`.

- [x] **Step 1: tests** — API tests with fake services (status codes, bodies, headers, scopes, idempotent replay of message POST, 422 for unknown override field / naive `from`, 204 body empty); integration test over HTTP: create conversation → first message (complete overrides) → follow-up with `departure_time` → messages list shows 4 messages newest first → recommendation history lists both → delete → 404.
- [x] **Step 2–4:** fail → implement → pass.

---

### Task 6: E2E, docs, verification, review

- [x] E2E: conversation with first message and follow-up against the compose stack; history lists the result.
- [x] Docs: spec §7.1 / §5.5 details and change log 0.8; data design change log (no schema change); structure D-52..D-57, §14 status, change log 0.8; README status and example.
- [x] Verification: ruff format/check, mypy, pytest (all), Docker rebuild + E2E, log scan.
- [x] Inline review, fixes, notes below; report to the user (they commit).

---

## Self-Review

- Spec coverage: E-08 (Tasks 3–5), E-09 (1, 3–5), E-10, E-11, E-12 (1, 3–5), E-13 (2–5), E-02 (1, 3–5), pagination rule §1 (1), overrides + re-assessment (2, 4), P-41/P-45 (4, existing worker).
- Types: `RequestOverrides`, `Page`, `Cursor`, `ConversationRecord`, `MessageRecord`, `RecommendationSummaryRecord`, `MessageReply` are defined in Tasks 1–4 and used with the same names in Task 5.

## Execution Notes (2026-09-17)

Tasks 1–6 were executed in order, test-first (RED = import error or failing assertion before the code). Differences from the plan:

- Task 1: the plan's checkboxes were ticked by mistake when the plan was written and reset before execution.
- Task 2: the missing-field check is written once, so mypy can narrow the optional fields.
- Task 3: the request loader moved to `app/infrastructure/db/repositories/requests.py` (with the point/preferences JSON helpers). `job_type_for()` lives in `app/domain/enums.py`, so the repository and the service share it. One repository test expected `limit` rows, but list methods return `limit + 1` by design; the test was corrected.
- Task 3: `ConversationRepository.list` was renamed `list_conversations`; a method called `list` hides the builtin in later annotations of the class (mypy `valid-type`).
- Task 4: the integration tests passed on the first run after the service was written. `SqlRecommendationRepository.sessions` was added so the test `Flow` can build the conversation repository from the same session factory.
- Task 5: the 200/201/202 response helper moved to `app/api/v1/responses.py` and is shared by both routers.
- Task 6: the README example was run against the Docker stack (first message with the trip, follow-up with only the new time).

### Code review (inline)

- Fixed: deleting a conversation while its synchronous follow-up was still running made `POST .../messages` return `500`, because the reply is not stored for a deleted conversation. It now returns `404` (`tests/unit/services/test_conversation_service.py`, failed first).
- Minor, open: `UNSUPPORTED_REGION` errors of a follow-up name the field without the `overrides.` prefix.
- Minor, open: a follow-up to a conversation whose last trip has already departed fails with `overrides.departure_time: in_past` until the user sends a new time (intended, but the Web App should show that hint).
- Checked: every repository read filters by `user_id`; messages and history reuse the existing indexes; follow-ups never read the cache; no message text is logged.

Final verification: see the step report.
