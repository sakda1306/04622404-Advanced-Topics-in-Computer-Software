# CareerMirror: API Contract

<!--
PURPOSE: The agreement between frontend and backend: endpoints, request/response shapes, error codes.
Change it only when both members agree (record the agreement in the change log below).
DOES NOT CONTAIN: why the system is built this way (Design.md), UI look (DesignSystem.md).
OWNER: both members.
-->

Related: [PRD.md](PRD.md), [Design.md](Design.md)

Status: v0.3 (1 Nov 2026), agreed by both members (v0.3b – v0.3e agreed by sakda1306 on 1 Nov 2026). Locked since 31 Oct 2026: change only through the change log.

## 1. Conventions

- **Base path**: `/api`. The browser calls the Next.js server, which proxies to `api` (`API_BASE_URL`, internal `http://api:8000`). The browser never calls `api` directly.
- **Format**: JSON, `application/json; charset=utf-8`. CV upload is `multipart/form-data`.
- **Auth**: httpOnly, `SameSite=Lax` cookie `access_token` (JWT HS256, 8 h, `JWT_TTL_HOURS`) set by register/login. Every endpoint except register, login and health requires it; missing or expired → `401 UNAUTHENTICATED`. Users can only read and change their own data. `/api/admin/*` also requires the user's email to be in `ADMIN_EMAILS`; otherwise `403 FORBIDDEN`.
- **Request id**: every response has header `X-Request-ID` (generated if the client did not send one). Quote it when reporting a bug.
- **IDs**: UUID strings. `role_id`, `skill_id` and `question_id` are readable slugs from `/data` in kebab-case for roles and skills, snake_case for questions (e.g. `backend-developer`, `rest-api`, `ws_teamwork`).
- **Time**: ISO 8601 with offset, Asia/Bangkok, e.g. `2026-11-03T14:05:00+07:00`.
- **Money**: integers in THB. Every salary figure carries `measure` and `source` (see `SalaryRange`).
- **Language**: field names in English; every text meant for the user (`message_th`, `answer`, `reason_th` …) is Thai.
- **Quota headers**: every response to an authenticated request carries
  `X-Quota-Requests-Remaining`, `X-Quota-Tokens-Remaining`, `X-Quota-Reset` (ISO time), so the UI can update without an extra call (FR-25).
- **Errors**: Problem-JSON (`application/problem+json`), same shape everywhere:

```json
{
  "type": "https://careermirror.local/errors/quota-exceeded",
  "title": "Daily quota exceeded",
  "status": 429,
  "code": "QUOTA_EXCEEDED",
  "message_th": "วันนี้คุณใช้โควตาถาม AI ครบแล้ว ระบบจะรีเซ็ตเวลา 00:00 น. ระหว่างนี้ยังลบทักษะหรือแก้ข้อมูลในโปรไฟล์ได้ตามปกติ",
  "request_id": "6f1c…",
  "details": { "reset_at": "2026-11-04T00:00:00+07:00" }
}
```

`code` is stable and is what `web` switches on; `message_th` can be shown as is. `details` is present only when the code below says so. `VALIDATION_ERROR` lists each problem as `details.fields: [{field, message, code}]`, where `field` is a dotted path such as `password` or `answers.0.value`; the submitted value is never echoed back.

- **Quota column** in the endpoint tables: **counts** = uses one request plus the tokens actually used; **no** = never calls the LLM and works when quota is exhausted.

## 2. Endpoints

### 2.1 Auth and account

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `POST /api/auth/register` | create account, record consent | `{email, password, display_name, consent: true}` | `{user: User}` + cookie | no |
| `POST /api/auth/login` | log in | `{email, password}` | `{user: User}` + cookie | no |
| `POST /api/auth/logout` | clear cookie | – | `{ok: true}` | no |
| `GET /api/auth/me` | current user | – | `{user: User}` | no |
| `DELETE /api/me` | delete the account and all its data: CV, answers, chat, profile, removed skills, edit proposals, quota counters, router logs, request and LLM call logs (FR-35) | `{confirm: "DELETE"}` | `{deleted: true}` + cookie cleared | no |
| `GET /api/health` | liveness | – | `{status: "ok", version}` | no |

- `register`: password ≥ 8 characters; `consent` must be `true` → otherwise `422 VALIDATION_ERROR`. Duplicate email → `409 EMAIL_TAKEN`.
- `login`: wrong email or password → `401 INVALID_CREDENTIALS` (same message for both). 5 failures per minute per email → `429 RATE_LIMITED`.

### 2.2 CV upload and parse (FR-0 – FR-4)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `POST /api/cv` | upload and parse a PDF; replaces any earlier CV | multipart field `file` (PDF ≤ 5 MB) | `{cv: CvParsed}` (status `draft`) | counts only if LLM extraction runs |
| `GET /api/cv` | current CV data | – | `{cv: CvParsed \| null}` | no |
| `PUT /api/cv/confirm` | save the user-corrected fields (FR-3) | `{skills: CvSkill[], education: Education[], experience: Experience[]}` | `{cv: CvParsed, completeness: Completeness}` | no |
| `DELETE /api/cv` | remove CV and the facts that came only from it | – | `{deleted: true, completeness: Completeness}` | no |

Errors: `415 CV_INVALID_TYPE` (not a PDF), `413 CV_TOO_LARGE`, `422 CV_UNREADABLE` (no text layer / scanned; OCR is out of scope).

- Rules always run. The LLM also extracts only if the user has quota left; that call counts toward quota. With no quota left the CV is parsed by rules only and the upload still succeeds: `POST /api/cv` never returns `QUOTA_EXCEEDED` (Design.md section 4.1).

### 2.3 Questionnaire (FR-5 – FR-7)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `GET /api/questionnaire` | questions from `data/questionnaire.json` | – | `{version, sections: [{id, title_th, questions: Question[]}], attribution: {text_th, sources: {title, url, license, license_url, attribution}[]}}` | no |
| `GET /api/questionnaire/answers` | saved answers (resume) | – | `{answers: {[question_id]: AnswerValue}, answered, total}` | no |
| `PUT /api/questionnaire/answers/{question_id}` | save one answer | `{value: AnswerValue}` | `{saved: true, completeness: Completeness}` | no |

Error: `404 QUESTION_NOT_FOUND`, `422 VALIDATION_ERROR` (value does not fit the question type, or a `multi` answer has more than `max_choices` items).

- File-only fields (`slot`, `trait`, `skill_id`, `source_ids`, `options_source`) are not sent. The api resolves `options_source` into `options` (skills from `data/skills.json`, roles from `data/roles.json`).
- `attribution` is what the questionnaire page footer shows (CC BY 4.0 for O*NET, DesignSystem.md section 5).

### 2.4 Chat and completeness (FR-8 – FR-13, FR-27)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `POST /api/chat` | send a message; AI Router picks the route | `{message}` (1–1000 chars) | `ChatResponse` | **counts** (rules-only replies such as `decline` count 1 request, 0 tokens) |
| `GET /api/chat/history` | earlier messages | `?limit=50&before=<message_id>` | `{messages: ChatMessage[]}` | no |
| `GET /api/profile/completeness` | sidebar meter | – | `Completeness` | no |

```jsonc
// ChatResponse
{
  "message_id": "uuid",
  "answer": "ข้อความภาษาไทย อ้างอิง [1] [2]",
  "route": "job_matching",            // skill_assessment | work_style | blind_spots | job_matching | salary | market | experience | profile_edit | clarify | decline | gap_question
  "sources": [Source],
  "edit_proposal": EditProposal | null,   // only when route = profile_edit
  "completeness": Completeness,            // updated if the message added facts
  "tokens_used": 812
}
```

FR-10 streaming (P1) would add `POST /api/chat/stream` (Server-Sent Events) with the same final payload; not part of v0.1.

### 2.5 Profile (FR-14 – FR-17, FR-27 – FR-34)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `POST /api/profile/generate` | build or rebuild the profile (user action only) | – | `{profile: Profile, matches: MatchList}` | **counts** |
| `GET /api/profile` | current profile | – | `{profile: Profile \| null}` | no |
| `GET /api/profile/edits/pending` | pending chat-edit proposals | – | `{edits: EditProposal[]}` | no |
| `POST /api/profile/edits/{edit_id}/confirm` | apply a proposal | – | `{profile: Profile, matches: MatchList}` | no |
| `POST /api/profile/edits/{edit_id}/reject` | discard a proposal | – | `{ok: true}` | no |
| `DELETE /api/profile/skills/{skill_id}` | remove button | – | `{profile: Profile, matches: MatchList}` (the UI confirms before calling) | no |
| `POST /api/profile/skills/{skill_id}/restore` | restore a removed skill from the removed list | – | `{profile: Profile, matches: MatchList}` | no |
| `GET /api/profile/removed-skills` | removed list (for restore) | – | `{skills: [{skill_id, name_th, removed_at}]}` | no |
| `PATCH /api/profile/preferences` | manual edit from form controls | `Partial<Preferences>` | `{profile: Profile, matches: MatchList}` | no |

- `generate` → `409 PROFILE_NOT_READY` when `can_generate` is false; `details.missing` lists the missing slots, required slots first, and `details.missing_required` lists only the required ones.
- `confirm` → `404 EDIT_NOT_FOUND`, `409 EDIT_EXPIRED` (15 min after the proposal), `409 EDIT_CONFLICT` (the field changed since the proposal).
- Profile endpoints before generation → `404 PROFILE_NOT_FOUND`.
- Every successful edit recomputes matches in Python and returns them; LLM-written reasons and next steps for changed roles come back with `explanations_stale: true` until `POST /api/roles/matches/explain` is called (FR-32).

### 2.6 Roles (FR-18 – FR-20b)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `GET /api/roles` | role catalogue (26 roles) | – | `{roles: [{role_id, title_th, title_en, summary_th, career_stage}]}` | no |
| `GET /api/roles/matches` | latest match results | – | `MatchList` | no |
| `POST /api/roles/matches/explain` | (re)write reasons and next steps for stale roles | – | `MatchList` | **counts** |
| `GET /api/roles/{role_id}` | one role with the user's match, gaps and next steps | – | `{role: RoleDetail, match: RoleMatch \| null}` | no |

Error: `404 ROLE_NOT_FOUND`.

### 2.7 Role market data (FR-21 – FR-22f)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `GET /api/roles/{role_id}/market` | salary layers, demand, listings from cache | `?listings=5` | `RoleMarket` | no |

- Always served from the cache; never waits on the provider. If no cache exists yet: `200` with `available: false` and `refreshing` telling whether a fetch is running.
- `web` polls every 5 s while `refreshing` is `true`.
- Data is Bangkok only (FR-22f); `location_scope` is always `"bangkok"` and the UI labels figures as Bangkok data.
- Requests never trigger a fetch. A scheduled job refreshes every role every 7 days (FR-22b); `refreshing` is `true` only while that job is fetching this role.

### 2.8 Quota (FR-23 – FR-25)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `GET /api/quota` | today's usage | – | `Quota` | no |

### 2.9 Admin (FR-40 – FR-45)

| method + path | purpose | request | response 200 | quota |
|---|---|---|---|---|
| `GET /api/admin/overview` | all dashboard panels in one call | `?window=today\|7d\|30d` (default `today`) | `AdminOverview` | no |

- Admin only: `403 FORBIDDEN` for any other account. Read-only, no LLM call, no provider call (FR-41).
- Aggregates only: no CV text, chat text, answers or emails in the response (FR-42).
- `window` applies to health, router and funnel; LLM usage and quota are always today (Asia/Bangkok); the cache table is always current.
- `web` calls it on page open, on the refresh button, and every 60 s while `/admin` is open.

## 3. Shared types

Shapes are written in TypeScript notation only because it is short and exact; it describes the JSON, not the code. The web is JavaScript (Design.md section 9) and may copy these shapes as JSDoc `@typedef` comments; the api uses Pydantic models with the same fields.

```ts
type User = { id: string; email: string; display_name: string; created_at: string;
              is_admin: boolean };   // email is in ADMIN_EMAILS; web shows the admin link only when true

type Evidence = {
  id: string;
  kind: "cv_line" | "answer" | "chat" | "rag_chunk" | "user_action";
  label_th: string;        // e.g. "CV บรรทัด 12", "แบบสอบถามข้อ 4", "คุณแก้ไขเอง"
  excerpt?: string;        // short quote shown in the citation popover
};

type Source = { n: number; evidence_id: string; label_th: string; url?: string };

type Skill = {
  skill_id: string; name_th: string; name_en: string;
  kind: "hard" | "soft";
  level: 1 | 2 | 3 | 4;    // 1 basic, 2 working, 3 strong, 4 expert
  years?: number;
  evidence_ids: string[];  // at least one
  edited_by_user: boolean;
};

type CvSkill = { name: string; skill_id?: string; level?: 1 | 2 | 3 | 4; line_no: number };
type Education = { school: string; degree?: string; field?: string; start?: string; end?: string; line_no?: number };
type Experience = { title: string; company?: string; start?: string; end?: string; months?: number; summary?: string; line_no?: number };

type CvParsed = {
  status: "draft" | "confirmed";
  filename: string;
  skills: CvSkill[]; education: Education[]; experience: Experience[];
  warnings_th: string[];   // e.g. "ไม่พบวันที่ของประสบการณ์บางรายการ"
};

type Question = {
  question_id: string;
  type: "single" | "multi" | "scale" | "skill_checklist" | "text";
  text_th: string;
  options?: { value: string; label_th: string; label_en?: string }[];   // label_en: roles only (from data/roles.json name_en)
  scale?: { min: 1; max: 5; min_label_th: string; max_label_th: string };
  max_choices?: number;                // multi only
  optional: boolean;
};
type AnswerValue = string | string[] | number | { skill_id: string; level: number }[];

type Completeness = {
  score: number;                       // 0-100
  can_generate: boolean;
  slots: { slot: "hard_skills" | "experience" | "education" | "work_style" | "soft_skills" | "goals";
           filled: boolean; required: boolean; points: number; max_points: number }[];
  missing_required: ("hard_skills" | "experience")[];   // required slots still empty; can_generate is false while non-empty
  inputs: { cv: "done" | "skipped"; questionnaire: "done" | "partial" | "skipped"; chat: "done" | "needed" };
  missing_th: string[];                // what to add next, shown in the sidebar
  profile_changes: ("cv" | "skills" | "work_style" | "soft_skills" | "goals" | "chat")[];
                                       // input parts changed since the profile was generated (a CV,
                                       // each questionnaire section id, chat facts); they reach the
                                       // profile and matches only when it is generated again. [] with
                                       // no profile. Skill remove/restore and chat edits change the
                                       // profile itself and never appear here.
};

type Preferences = {
  interested_roles: string[];          // role_id
  desired_salary_thb?: number;         // monthly
  locations: string[];
  work_style: { [trait: string]: number };   // 0..1, self-reported; keys: teamwork, structure, ambiguity, pressure, innovation, leadership
};

type Claim = { text_th: string; evidence_ids: string[]; edited_by_user: boolean };

type Profile = {
  profile_version: number;
  generated_at: string; updated_at: string;
  hard_skills: Skill[]; soft_skills: Skill[];
  work_style: { summary_th: string; traits: { trait: string; value: number; label_th: string }[];
                disclaimer_th: string };          // "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ" (DesignSystem.md section 5)
  experience: { total_months: number; summary: Claim[] };
  blind_spots: Claim[];
  preferences: Preferences;
  evidence: { [evidence_id: string]: Evidence };
};

type Gap = { gap_id: string; kind: "missing_skill" | "below_level" | "soft_skill";
             skill_id: string; name_th: string; required_level?: number; user_level?: number };
type NextStep = { gap_id: string; action_th: string; priority: 1 | 2 | 3 | 4 | 5 };

type RoleMatch = {
  role_id: string; title_th: string;
  match_pct: number;                   // computed in Python
  breakdown: { hard_required: number; hard_nice: number; soft: number; work_style: number };
  matched: { skill_id: string; name_th: string; evidence_ids: string[] }[];
  gaps: Gap[];
  reason_th: string | null;            // LLM, cites evidence
  next_steps: NextStep[];              // LLM, each tied to a gap
  explanations_stale: boolean;
};

type MatchList = {
  profile_version: number;
  threshold: number;
  below_threshold: boolean;            // true = none passed; roles are the closest ones (FR-19a)
  roles: RoleMatch[];                  // ≤ TOP_N (5)
};

type RoleDetail = { role_id: string; title_th: string; title_en: string; description_th: string;
                    career_stage: "entry" | "mid" | "senior";
                    required: { skills: { skill_id: string; name_th: string }[];   // one item, or the any_of group (any one is enough)
                                min_level: number; weight: 1 | 2 | 3 }[];
                    nice_to_have: { skill_id: string; name_th: string }[];
                    soft_skills: { skill_id: string; name_th: string }[];
                    learning_path_th: string;                                   // from data/roles/<role_id>.md
                    author: string; reviewer: string; status: "draft" | "reviewed";
                    sources: { url: string; language: "th" | "en"; file?: string }[] };

type SalaryRange = {
  min_thb: number; max_thb: number;
  measure: "monthly_base" | "annual_total";
  source: string;                      // "JobThai (ประกาศงาน)", "ตารางอ้างอิงของทีม", "สำนักงานสถิติแห่งชาติ"
  source_type: "advertised" | "curated_reference" | "official_baseline";
  sample_size?: number;                // advertised layer: postings with a parseable salary
  as_of: string;                       // date the figure refers to / was retrieved
  url?: string;
};

type Listing = { title: string; company: string; location?: string; salary_text?: string; posted_at?: string; url: string; source: string };

type RoleMarket = {
  role_id: string;
  location_scope: "bangkok";
  available: boolean;
  fetched_at: string | null;
  stale: boolean;                      // older than CACHE_MAX_AGE_DAYS or last refresh failed
  refreshing: boolean;
  salary: { advertised: SalaryRange | null; reference: SalaryRange | null; baseline: SalaryRange | null };
  demand: { posting_count: number; trending_skills: { skill_id: string; name_th: string; count: number }[] } | null;
  listings: Listing[];                 // no contact fields (FR-22e)
  disclaimer_th: string;               // unofficial source, team-curated
};

type EditChange = { op: "set" | "add" | "remove"; field: string; skill_id?: string;
                    old_value: unknown; new_value: unknown; restores_removed_skill?: boolean };
type EditProposal = { edit_id: string; changes: EditChange[]; summary_th: string;
                      expires_at: string; status: "pending" | "applied" | "rejected" | "expired" };

type Quota = { day: string; requests_used: number; requests_limit: number;
               tokens_used: number; tokens_limit: number; reset_at: string; exhausted: boolean };

type AdminOverview = {
  generated_at: string; window: "today" | "7d" | "30d";
  warnings: { panel: "health" | "llm" | "quota" | "cache" | "router"; code: string; message_th: string }[];
  health: { api: "ok"; db: "ok" | "down"; last_request_at: string | null; requests: number;
            error_rate: number;                                   // 0..1, 5xx and LLM errors / requests
            errors_by_code: { code: string; count: number }[];
            llm_latency_ms: { p50: number; p95: number; target: 15000 } };
  llm: { day: string; models: { model: string; role: "main" | "router" | "fallback";
                                tokens_used: number; tokens_limit: number;
                                requests_used: number; requests_limit: number }[];
         rate_limited_429: number; fallback_calls: number };
  quota: { requests_used: number; tokens_used: number; users_active: number;
           users_exhausted: number; users_over_80pct: number };
  cache: { apify_runs_this_week: number; apify_runs_budget: 26;
           roles: { role_id: string; title_th: string; fetched_at: string | null; age_days: number | null;
                    stale: boolean; refreshing: boolean; last_error: string | null;
                    posting_count: number; salary_parsed_share: number;      // 0..1
                    has_reference_salary: boolean }[] };
  router: { messages: number; by_route: { route: string; share: number }[];
            by_layer: { rules: number; llm: number; guard: number };        // shares 0..1
            clarify_rate: number; decline_rate: number; low_confidence_rate: number };
  funnel: { registered: number; with_cv_or_questionnaire: number; profile_generated: number; role_opened: number;
            cv_unreadable_rate: number;
            input_mix: { cv_only: number; questionnaire_only: number; both: number };
            avg_completeness_at_generate: number;
            edits: { applied: number; rejected: number; expired: number };
            top_removed_skills: { skill_id: string; name_th: string; count: number }[] };   // top 5
};

type ChatMessage = { message_id: string; role: "user" | "assistant"; text: string; route?: string;
                     sources?: Source[]; created_at: string };
```

Editable fields for chat edits and `PATCH /api/profile/preferences` (allow-list): `preferences.interested_roles`, `preferences.desired_salary_thb`, `preferences.locations`, `preferences.work_style.*`, `skills[skill_id].level`, `skills[skill_id].years`, add a skill, remove a skill. Anything else → `422 EDIT_FIELD_NOT_ALLOWED`.

## 4. Error codes

| code | HTTP | meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | body or query does not match the schema; `details.fields` lists problems |
| `UNAUTHENTICATED` | 401 | no or expired cookie |
| `INVALID_CREDENTIALS` | 401 | wrong email or password |
| `EMAIL_TAKEN` | 409 | register with an existing email |
| `RATE_LIMITED` | 429 | too many requests in a short window (login, chat burst); `Retry-After` header |
| `QUOTA_EXCEEDED` | 429 | daily request or token limit reached; `details.reset_at`, `details.reason` (`requests` / `tokens`); no LLM call made |
| `CV_INVALID_TYPE` | 415 | file is not a PDF |
| `CV_TOO_LARGE` | 413 | file over 5 MB |
| `CV_UNREADABLE` | 422 | PDF has no extractable text (scanned) |
| `QUESTION_NOT_FOUND` | 404 | unknown `question_id` |
| `PROFILE_NOT_READY` | 409 | no CV/questionnaire, a required slot empty, or completeness below threshold; `details.missing`, `details.missing_required` |
| `PROFILE_NOT_FOUND` | 404 | profile not generated yet |
| `EDIT_NOT_FOUND` | 404 | unknown or foreign `edit_id` |
| `EDIT_EXPIRED` | 409 | proposal older than its expiry |
| `EDIT_CONFLICT` | 409 | field changed since the proposal was made |
| `EDIT_FIELD_NOT_ALLOWED` | 422 | change outside the allow-list |
| `SKILL_NOT_FOUND` | 404 | skill not in the profile (remove) or not removed (restore) |
| `ROLE_NOT_FOUND` | 404 | unknown `role_id` |
| `LLM_UNAVAILABLE` | 503 | Groq error or rate limit after retries; quota is refunded |
| `LLM_TIMEOUT` | 504 | Groq did not answer in time; quota is refunded |
| `FORBIDDEN` | 403 | signed in, but not allowed (admin endpoints for a non-admin account) |
| `INTERNAL_ERROR` | 500 | unexpected; no stack trace in the body |

Generic codes for requests that fail outside an endpoint's own rules (v0.2). `web` treats them as "something is wrong with the request" and shows `message_th`; they never need special handling per screen.

| code | HTTP | meaning |
|---|---|---|
| `BAD_REQUEST` | 400 | body could not be read, e.g. a broken multipart upload |
| `NOT_FOUND` | 404 | unknown path (resource-specific 404s use their own codes above) |
| `METHOD_NOT_ALLOWED` | 405 | path exists but not with this method |
| `PAYLOAD_TOO_LARGE` | 413 | JSON body over 64 KB (the CV upload uses `CV_TOO_LARGE`) |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | body is not `application/json` (or not `multipart/form-data` on `POST /api/cv`) |
| `HTTP_ERROR` | any other 4xx | fallback; `status` in the body is the real HTTP status |

## 5. Change log

| Date | Change | Agreed by |
|---|---|---|
| 2026-10-31 | v0.1 draft: all endpoint groups, shared types, error codes | sakda1306 (draft, waiting for Automatic28m) |
| 2026-10-31 | v0.2: six generic error codes (`BAD_REQUEST`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `PAYLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `HTTP_ERROR`); shape of `details.fields` for `VALIDATION_ERROR`. Raised in the review of PR #4. No endpoint or type changes. | sakda1306 (waiting for Automatic28m) |
| 2026-11-01 | v0.3a, already in `develop` (PR #11, #12): `Completeness.slots[].required` and `Completeness.missing_required` (PRD FR-14); `PROFILE_NOT_READY` adds `details.missing_required`; `DELETE /api/profile/skills/{skill_id}` no longer returns `undo_until` (the UI confirms first, PRD open question 7). | Automatic28m; merged by sakda1306 in PR #11 |
| 2026-11-01 | v0.3b: role and skill ids are kebab-case; `Question.max_choices`; questionnaire `attribution` block; `POST /api/cv` never returns `QUOTA_EXCEEDED` (rules-only fallback); `DELETE /api/me` scope (FR-35); `RoleDetail` gets `career_stage`, `any_of` skill groups, `weight`, `soft_skills`, `learning_path_th`, author/reviewer/status, and a `sources` shape that matches `data/roles/*.json`; `GET /api/roles` adds `career_stage`; `RoleMarket.location_scope`; scheduled refresh only; the 8 h session, 15 min edit expiry and 5 s polling are confirmed. | Automatic28m, sakda1306 |
| 2026-11-01 | v0.3c (text only, no shape change): the `Profile.work_style.disclaimer_th` example uses the DesignSystem wording ("ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ"); user-facing Thai says "ทักษะ", not "สกิล" (the `QUOTA_EXCEEDED` example). The api messages in `api/app/core/errors.py` for `QUOTA_EXCEEDED` and `SKILL_NOT_FOUND` ("ไม่พบทักษะนี้ในโปรไฟล์") need the same change; section 2.7 heading now lists FR-22f. | Automatic28m, sakda1306 |
| 2026-11-01 | v0.3d: admin dashboard (PRD FR-40 – FR-45): `GET /api/admin/overview` with `AdminOverview`; `User.is_admin`; new error code `403 FORBIDDEN`; `/api/admin/*` requires an email in `ADMIN_EMAILS`; `DELETE /api/me` also removes the user's request and LLM call log rows. | Automatic28m, sakda1306 |
| 2026-11-02 | v0.3f: `Question.options[].label_en` (optional, roles only) so `go_interested_roles` can show the English role name next to the Thai one. Additive; old clients ignore it. | Automatic28m; needs sakda1306's review (api folder) |
| 2026-11-01 | v0.3e (text only, no shape change): section 3 states that the TypeScript notation describes JSON shapes only; the web is written in JavaScript. | Automatic28m, sakda1306 |
| 2026-11-05 | v0.3g: `Completeness.profile_changes` lists the input parts (CV, questionnaire section, chat) changed since the profile was generated, so the web can ask the user to generate it again. Additive; old clients ignore it. | Automatic28m; needs sakda1306's review (api folder) |
