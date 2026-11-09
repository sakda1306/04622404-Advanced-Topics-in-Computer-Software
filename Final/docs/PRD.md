# CareerMirror: Product Requirements Document

Status: DRAFT. Items marked (assumed) are proposals, not yet confirmed by the team.
Source of truth for scope. Architecture lives in `Design.md`, UI rules in `DesignSystem.md`, endpoints in `Contract.md`. Link to them; do not copy their content here.

## 1. Overview

CareerMirror is a Thai-language web app that helps a job seeker understand themselves before applying. The user provides a CV (PDF), answers a questionnaire, or both, and chats with an AI. The app builds a profile (hard/soft skills, work-style preferences, experience, blind spots) and then shows the IT roles that fit the user (match %, next steps to close the gaps), plus salary range and market demand for a role the user picks, each with reasons and cited evidence.

Positioning: self-understanding first, job matching as the payoff. Not a job board.

Domain: computer/IT roles only (for example AI Engineer, Software Engineer, Full-stack Developer, and related backend, frontend, data, ML, DevOps and QA roles). Other fields are out of scope.

Context: course final project (Advanced Topics in Computer Software, RMUTT). Start 31 Oct 2026, deadline 5 Nov 2026. Scope is MVP only.

## 2. Problem

- Fresh graduates and career changers often cannot name their own strengths, gaps or fit, so CVs and job choices are generic.
- Job boards show listings but not why a role fits a specific person.
- Generic AI chat gives unexplained, inconsistent scores.

## 3. Goals and non-goals

Goals
1. Produce a profile the user recognises as accurate and useful.
2. Show job match % that is explainable and traceable to evidence.
3. Keep LLM cost bounded with a per-user daily quota.
4. Ship a working, demoable MVP by 5 Nov 2026.

Non-goals (future work, mention in the report): non-IT jobs, job tracker, interview prep, profile versioning, full PDPA tooling, a sanctioned live job-board partnership (the MVP uses unofficial scraped data, see 6.7).

## 4. Target users

- Primary: Thai fresh graduates and early-career job seekers.
- Secondary: career changers who want to see how existing skills map to new roles.

Not targeted: recruiters, employers.

## 5. User journey

1. Land on the app and read a short intro. Register with email and password (accepting the consent notice is required) or log in (FR-26).
2. Provide input data. The user chooses one or both of the following, in any order:
   - Upload CV (PDF). App parses it and shows extracted skills and experience for confirmation.
   - Complete the questionnaire.
3. Chat with the AI to fill gaps. A sidebar shows profile completeness (0-100%).
4. Press "Generate profile" (user action, never automatic).
5. View the profile, then the IT roles above the match threshold (match %, reasons, next steps to close the gaps).
6. Pick a role to see its salary range, market demand and real listings.
7. Refine the profile at any time after it is generated: tell the AI chat what to change (preferences, skill details), or remove a skill with its remove button. Matches and the role views refresh from the updated profile.

## 6. Functional requirements

Priority: P0 = must ship, P1 = ship if time allows.

### 6.1 CV upload and parsing (P0)
- FR-0 CV upload is optional. A user may skip it and use the questionnaire only (see FR-5a).
- FR-1 Accept a PDF CV up to 5 MB. Reject other types with a Thai error message.
- FR-2 Extract text, then structured fields: skills, education, experience entries.
- FR-3 Show extracted data to the user and let them correct it before it is used.
- FR-4 Handle unreadable or scanned PDFs with a clear message (OCR is out of scope).

### 6.2 Questionnaire (P0)
- FR-5 A fixed questionnaire covering an IT tech-stack skills checklist, work-style preferences (for example teamwork vs. solo, structure vs. ambiguity), motivation and soft skills (22 questions in `data/questionnaire.json`).
- FR-5a The questionnaire is optional. A user may skip it and use the CV only. At least one of CV or questionnaire is needed before "Generate profile" is enabled (see FR-14).
- FR-6 Answers are saved per question so the user can resume.
- FR-7 Answers feed skill, work-style and soft-skill assessment. No MBTI or personality-type diagnosis is used.

### 6.3 Chat with progress sidebar (P0)
- FR-8 Chat asks follow-up questions to fill gaps in whichever of CV and questionnaire data the user provided. If only one was given, chat covers what the other would have supplied.
- FR-9 Sidebar shows the completeness meter (0-100%) and which of CV, questionnaire and chat are still missing. A skipped CV or questionnaire is shown as "optional", not as an error.
- FR-10 Responses stream to the UI (P1).

### 6.4 AI Router (P0)
- FR-11 For each request, route to exactly one of: skill assessment, work style, blind spots, job matching (with next steps), salary, market, experience, profile edit (see 6.10).
- FR-12 Each route fetches only the data it needs (RAG, cached external data, or local scoring) and sends the minimum personal data to the LLM.
- FR-13 Router decision is logged for debugging.

### 6.5 Profile generation (P0)
- FR-14 "Generate profile" is enabled only when all of these hold: (1) at least one of CV or questionnaire is provided; (2) the required slots are filled: at least 3 hard skills, each with a level, and experience entries or a stated "no experience"; (3) completeness is at least 65% (`COMPLETENESS_THRESHOLD`, re-checked in the 3 Nov calibration). The meter is scored so that a CV-only or questionnaire-only user can reach the threshold with one or two chat answers. When generation is blocked, the sidebar names the missing required slots first.
- FR-15 Profile sections: hard skills, soft skills, work-style preferences, experience summary, blind spots.
- FR-16 Every claim cites evidence: a CV line, a questionnaire answer, or a RAG source.
- FR-17 Work-style preferences are shown as self-reported preferences, not as a personality diagnosis or fact.

### 6.6 Role matching (P0)
Matching is profile versus a fixed list of IT role profiles, not versus individual job postings.
- FR-18 Maintain a fixed list of 26 IT role profiles in `/data/roles/` (the roles in `data/roles.json`). Each has weighted required and nice-to-have hard skills, soft skills, work-style traits, a prose description and learning-path text for RAG, and records who wrote it and its sources.
- FR-18a Compute match % in plain Python from the overlap between profile skills and role skills. Hard skills dominate; work-style has a low weight. Embeddings only map free-text skills to the skill taxonomy and retrieve explanation text; they never produce the %. The LLM only explains the result.
- FR-19 Show only roles at or above the match threshold of 60% (`MATCH_THRESHOLD`, re-checked in the 3 Nov calibration with sample profiles: student, full-stack developer, ML developer). For each role show: match %, matched skills, missing skills, and a short reason with cited evidence.
- FR-19a If no role passes the threshold, show the closest roles and what is missing.
- FR-20 Show at most the top 5 roles above the threshold (`TOP_N_ROLES`).
- FR-20a Next steps / gap to close: for each shown role, list prioritised actions (skills to learn, CV edits), each tied to a specific missing skill or gap. Gaps come from the scoring step; the LLM only words the actions.
- FR-20b The user picks a role from the results to open its salary, market and listings view (6.7).

### 6.7 Salary and market (P0)
Data comes from real Thai sources, not seeded samples. See `Design.md` for the data provider design.
- FR-21 Show a salary range for the picked role in two layers, always with source, measure (monthly base pay vs. annual total compensation) and date: (1) ranges advertised in job postings, parsed from the source text; (2) a hand-curated reference table in `/data` (source, URL and retrieved date per role), with the NSO IT-industry wage as a sanity check. Do not present a single figure as the true salary.
- FR-22 Show a market demand summary (posting count, trending skills) and a few real listings for the picked role, from the cached postings.
- FR-22a Job and salary data is cached per role with a `fetched_at` date. The cache is shared across all users: one copy per role, never fetched per user. The cache is seeded before the demo with one fetch per role, which is the guaranteed baseline.
- FR-22b A scheduled backend job refreshes every role's cache once every 7 days. User actions (matching, opening a role) never trigger a fetch; they always read the cache. The report never waits on the data API. If a refresh fails, keep and show the previous cached data labelled with its date, and retry at the next scheduled run.
- FR-22c Fetch budget: each refresh requests up to 20 postings per role (all roles in `data/roles.json`, currently 26), which is 26 runs and about 520 results per week, and about 104-130 runs (about 2,080-2,600 results) per month. Any change to the role count or results per role must be checked against the API credit before it is made.
- FR-22d Show the "last updated" date (`fetched_at`) in the role view, and a loading state only while a refresh of that role is running.
- FR-22e Collect only job-level fields needed for the feature. Do not collect employer contact details (emails, phone numbers, LINE IDs).
- FR-22f Fetch only jobs located in Bangkok. Set the location filter in the API request, and drop any posting whose location is not Bangkok at ingest. Salary and market figures are labelled as Bangkok data in the UI.

### 6.8 Quota (P0)
- FR-23 Enforce a per-user daily request and token limit in the backend before any LLM call.
- FR-24 When exceeded, return a Thai message with the reset time. No LLM call is made.
- FR-25 Show remaining quota in the UI (P1).

### 6.9 Identity (P0)
- FR-26 Email and password login (decided 31 Oct 2026; see [Design.md](Design.md) and [Contract.md](Contract.md)). Consent is recorded at registration. Quota and saved data are keyed to the user account, so they survive a browser change.
- FR-35 Delete account: the user can delete their account from the Account page (`/account`) after typing "DELETE" to confirm (`DELETE /api/me`). This removes the account and all its data (CV text and parsed fields, questionnaire answers, chat history, profile, removed skills, edit proposals, quota counters and router logs), clears the session, and cannot be undone. Shared role caches are not user data and are kept. No LLM call, no quota.

### 6.10 Profile editing after generation (P0)
The generated profile is editable. Edits are in place; keeping old profile versions stays out of scope.
- FR-27 Edit by chat: the user can tell the AI to change profile details, either preferences (for example desired role, work style, location, salary expectation) or the details of a specific skill (for example level, years of experience). The AI states the exact change it will make, and the user confirms before it is applied.
- FR-28 Edit by command is handled by the AI Router's "profile edit" route. The LLM extracts a structured change (field, old value, new value); the backend validates and applies it. The LLM never writes to the profile directly.
- FR-29 Skill list with remove: hard and soft skills are shown as a list, and each item has a remove button. Pressing it opens a short confirmation; the skill is removed only after the user confirms (decided 1 Nov 2026). Removed skills can be restored from the removed list.
- FR-30 The remove button is a direct UI action. It makes no LLM call and uses no quota.
- FR-31 A removed skill is excluded from job matching, and the AI does not re-add it from the CV or chat unless the user asks for it.
- FR-32 After any edit, match %, reasons and next steps are recomputed from the updated profile, and the role views (salary, market) refresh. Scoring stays in plain Python.
- FR-33 User-edited items are labelled "edited by you". For these, the cited evidence is the user's own statement or action, which satisfies the evidence rule (FR-16).
- FR-34 Chat edits count toward the daily quota (FR-23). If the quota is exceeded, the remove button and manual changes still work.

### 6.11 Appearance: light and dark theme (P0)

- FR-36 The app has a light theme and a dark theme. A theme toggle offers three options: สว่าง (light), มืด (dark) and ตามระบบ (follow the operating system's `prefers-color-scheme`). ตามระบบ is the default.
- FR-37 The toggle is in the top bar of every page, including Landing, Register and Login, so it works before login. Switching is instant: no page reload, and no loss of form, questionnaire or chat input.
- FR-38 The choice is saved in the browser only (not in the account, no API call, no quota). It is applied before the first paint, so the page never flashes the wrong theme.
- FR-39 Every screen, state and chart works in both themes and meets WCAG 2.1 AA in both. Colours come from the named brand colours in [CIBrand.md](CIBrand.md), which define a light and a dark value for each name; UI rules are in [DesignSystem.md](DesignSystem.md).

### 6.12 Admin dashboard (P0)

A read-only page for the team to monitor the app, mainly to catch problems before the demo. Data shapes are in [Contract.md](Contract.md), data sources in [Design.md](Design.md), the page in [DesignSystem.md](DesignSystem.md).

- FR-40 Admin access: only accounts whose email is listed in `ADMIN_EMAILS` (the two team members) can open `/admin` and call `/api/admin/*`. Anyone else gets `403 FORBIDDEN`, and the admin link is not shown to them. Admins log in like other users.
- FR-41 The dashboard is read-only: it never changes data, never starts a cache refresh, makes no LLM call and uses no quota.
- FR-42 It shows only totals, rates and per-role data. It never shows CV text, chat messages, questionnaire answers, emails or password data, and it never lists individual users.
- FR-43 Panels (P0), each for a time window of today, 7 days or 30 days where it applies:
  - (a) Health: API and database status, last request time, request count, error rate by error code (`LLM_UNAVAILABLE`, `LLM_TIMEOUT`, `INTERNAL_ERROR`, `RATE_LIMITED` first), and p50 / p95 latency of LLM calls against the 15 s target.
  - (b) LLM usage: tokens and requests today per Groq model against the account limits (200,000 tokens and 1,000 requests per day per model), the count of 429 responses and of fallback-model calls.
  - (c) User quota: total requests and tokens used today, users who reached the daily limit, users above 80% of it.
  - (d) Job-data cache: one row per role with cache age (`fetched_at`), stale / refreshing state, last error, posting count, share of postings with a parseable salary, and whether the role has a reference salary; Apify runs this week against the budget of 26 (FR-22c).
  - (e) AI Router: share of each route, share decided by rules vs. LLM, and the `clarify`, `decline` and low-confidence rates.
  - (f) User funnel: registered → CV or questionnaire → profile generated → role opened; CV unreadable rate; CV-only / questionnaire-only / both; average completeness when generating; chat edits confirmed / rejected / expired; most removed skills.
- FR-44 Warning states: a panel value turns to warning when it passes a threshold (LLM tokens or requests above 80% of the daily limit, error rate above 5%, a role cache older than 7 days or with an error, Apify runs above the weekly budget). Thresholds are config values, not hardcoded.
- FR-45 The page loads the data on open, has a refresh button, and refreshes itself every 60 s while open (assumed).
- FR-46 (P1) Match quality: profiles with no role above the threshold, match % distribution, most matched roles and most common gaps. Needs stored match results.

## 7. Non-functional requirements

- Language: all user-facing text in Thai; code, comments and docs in English.
- Performance: non-LLM pages respond in under 1 s; LLM responses target under 15 s.
- Privacy: collect minimal personal data; show a consent notice; allow the user to delete their account and data (FR-35); do not log CV text; send the LLM only what the route needs. The admin dashboard shows aggregates only (FR-42).
- Secrets: in `.env`; commit only `.env.example`. Model name via env var.
- Security: passwords are hashed with bcrypt and never logged or returned; failed logins are rate-limited per email; the session token is a JWT in an httpOnly cookie, signed with `JWT_SECRET` from `.env` only.
- Reliability: handle Groq rate limits and errors with a retry, then a switch to the fallback model (Design.md section 4.7), then a friendly Thai message. Keep each LLM prompt under about 5K tokens so one request fits the 8K tokens-per-minute limit. Handle job-data API failures by falling back to the cache (FR-22b).
- Data terms: the job data scraper (Apify JobThai) is unofficial. The team does not review the site's terms (decided 1 Nov 2026; accepted risk). Use public listings only, stay within the weekly fetch budget (FR-22c), collect no contact data (FR-22e), and state in the report that the source is unofficial and its terms were not reviewed.
- Deployment: `docker compose up --build` starts the whole app (see [Design.md](Design.md) section 8).

## 8. Data

- Authored in `/data`: 26 structured IT role profiles (FR-18), RAG source documents for those roles, a skill taxonomy, and the curated salary reference table (FR-21).
- Fetched and cached per role (Bangkok only, refreshed every 7 days, shared across users; FR-22a to FR-22f): Thai job postings and advertised salaries, via the Apify JobThai scraper (decided 1 Nov 2026). Salary arrives as text and is parsed. Many postings may not state a salary. NSO / data.go.th wage data is used for the IT-industry baseline only (by industry, not job title).
- Every salary or market figure shows its source, measure and date in the UI. Hand-written role profiles and the reference table are labelled as team-curated.
- User data: account (email, password hash, display name, consent timestamp), CV text and parsed fields, questionnaire answers, chat history, generated profile, removed skills, profile edit proposals, quota counters, router logs, request logs and LLM call logs. All of it is removed when the user deletes the account (FR-35).

## 9. Success metrics

MVP is a course project, so metrics are checked in the demo and a small test, not in production analytics.

| Metric | Target |
|---|---|
| End-to-end flow (CV to match results) works in demo | 100% of rehearsed runs |
| Claims in profile and matches with cited evidence | 100% |
| Testers (5) who rate the profile "accurate" or better | at least 4 of 5 |
| LLM call blocked correctly when quota exceeded | pass |
| Time from first input (CV or questionnaire) to results | under 10 min for a first-time user |
| CV-only and questionnaire-only users can each generate a profile | pass |
| Chat edit and skill remove update the profile and matches | pass |
| Each shown role has next steps tied to a specific gap | 100% |
| Role view works with the job-data API unavailable (cache fallback) | pass |
| Every salary figure shows source, measure and date | 100% |
| Admin dashboard shows LLM budget, cache state and errors correctly during rehearsal | pass |
| A non-admin account gets 403 on `/admin` and `/api/admin/*` | pass |

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| 6-day deadline | Hold MVP scope; P1 items are cut first; ship the pre-seeded cache before the background refresh (FR-22b) |
| Job-data API slow, capped or down at demo time (free Apify plan caps a run at 20 jobs) | Seed the cache before the demo; read from the cache; refresh in the background only |
| Scraped data is unofficial and may break or breach site terms (terms not reviewed; accepted risk) | Public listings only, small weekly volume, no contact data, disclose in the report; curated reference table as backup |
| Few postings state a salary; sources disagree on pay | Show two labelled layers and ranges, never one figure; state measure and date |
| Hand-written role profiles are generic or biased | Weight hard skills most, cite sources, test with sample profiles |
| Match threshold too strict or too loose | Calibrate with sample profiles; show closest roles when none pass (FR-19a) |
| CV parsing quality varies | User confirms and edits parsed data (FR-3) |
| LLM hallucinated claims | Require cited evidence; scoring in Python; LLM only explains |
| Groq rate limits or free-tier caps (8K tokens/min, 200K tokens/day per model, shared across the Groq account) | Daily quota, retries, fallback model, prompts under ~5K tokens, separate Groq account for the demo |
| Embedding model for Thai | `intfloat/multilingual-e5-base` (decided); verify with the Thai golden set on day 1, switch to `BAAI/bge-m3` if hit@3 is below 0.8 |
| Work-style results misread as a diagnosis | Label as self-reported preferences; low weight in the score |
| Personal data exposure | Minimal data to the LLM, deletion option, no CV text in logs |
| Stolen or guessed credentials | Hashed passwords, login rate limit, httpOnly cookie, secret only in `.env` |
| Groq daily tokens or Apify credits run out during the demo | Admin dashboard (FR-43b, FR-43d) with warnings at 80% of the limit; check it before every rehearsal |
| Admin data exposes users | Admin role from `ADMIN_EMAILS` only, aggregates only, no content or emails (FR-40, FR-42) |

## 11. Milestones

Detailed plan in [Schedule.md](Schedule.md).

| Date | Milestone |
|---|---|
| 31 Oct | Scaffold, Docker Compose, API contract agreed; auth (register, login, JWT cookie) so the frontend can call protected endpoints; test one small JobThai scraper run (salary coverage, description quality) |
| 1-2 Nov | CV parsing, questionnaire, quota, router skeleton; port the retrieval module into the api; role profiles drafted 1 Nov (26 roles, need a human review); write the salary reference table |
| 3 Nov | Chat, profile builder, scoring and RAG; seed the per-role cache; calibrate the threshold |
| 4 Nov | Match with next steps, role view (salary, market, listings); admin dashboard (FR-40 – FR-45); background refresh if time allows; Thai copy; check every screen in light and dark theme (FR-39); bug fixes |
| 5 Nov | Report, demo rehearsal, submission |

## 12. Open questions

1. ~~Login: anonymous session or email?~~ Decided 31 Oct 2026: email and password login (FR-26).
2. ~~Groq model choice and its daily limits.~~ Decided 1 Nov 2026: `openai/gpt-oss-120b` for profile generation, match explanations and next steps; `qwen/qwen3.8-27b` for the router, profile-edit and CV extraction, chat follow-ups, and as fallback on 429/413. Daily quota per user: 40 requests and 40,000 tokens (assumed until tested). Details in [Design.md](Design.md) section 4.7.
3. ~~Completeness threshold for enabling profile generation (60% is a guess).~~ Decided 1 Nov 2026: required slots (hard skills with levels, experience) plus a score of at least 65% (FR-14). A percentage alone could pass a profile with no hard skills, which makes matching meaningless. 65 is still calibrated with sample profiles on 3 Nov. Details in [Design.md](Design.md) section 4.1.
4. ~~Work-style questionnaire source: custom, or based on a public framework (not MBTI)?~~ Decided 1 Nov 2026: team-written items built on O*NET Work Styles (CC BY 4.0). The O*NET questionnaires (Knowledge, Work Activities, Work Context) ask workers to rate their job, not themselves, so they are not used as-is; only the O*NET descriptor names and definitions are adapted. Attribution and a note that the team adapted the content are required (see [Design.md](Design.md) section 6). Not MBTI.
5. ~~Job-data source: Apify JobThai/JobsDB (paid beyond 20 jobs per run) or Techmap (Thailand coverage unverified)? Who checks the sources' terms?~~ Decided 1 Nov 2026: Apify JobThai only. Nobody reviews the site's terms; this is an accepted risk, disclosed in the report (§7 Data terms).
5a. ~~Fixed role list: confirm the ~10 roles, and who writes and reviews the role profiles.~~ Decided 1 Nov 2026: the 26 roles in `data/roles.json`. Profiles are in `data/roles/` (status `reviewed` since 3 Nov 2026); the author is Phanlop Boonleua and the reviewer is sakda1306. Every required skill cites a source, using the files in `pdf/` instead of the Bangkok postings first planned.
5b. ~~Match threshold is a guess until tested.~~ Decided 1 Nov 2026: 60 (`MATCH_THRESHOLD`). Scoring the three sample profiles against the 26 drafted role profiles gave 2-4 roles each at 60, with each sample's own role ranked first. Re-checked in the 3 Nov calibration ([Design.md](Design.md) section 10). (Cache refresh is decided: every 7 days, Bangkok only, shared across users.)
6. ~~Is Postgres needed, or is SQLite enough for the demo?~~ Decided 1 Nov 2026: Postgres for app data, as a `db` container in Docker Compose. The RAG retrieval store stays a SQLite file inside `api` (see [Design.md](Design.md) section 5).
7. ~~Profile editing: confirm-before-apply for chat edits, and confirmation or undo for skill removal. Is this the right balance between safety and speed?~~ Decided 1 Nov 2026: confirm before any change is applied, for both chat edits (FR-27) and skill removal (FR-29). No undo toast; removed skills can be restored from the removed list.
