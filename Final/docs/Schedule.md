# CareerMirror: Schedule

<!--
PURPOSE: The detailed day-by-day work plan and who does what. PRD.md section 11 keeps only the milestones;
this file holds the task-level detail and progress. Update it daily.
DOES NOT CONTAIN: requirements (PRD.md), design (Design.md).
-->

Timeline: 31 Oct 2026 to 5 Nov 2026. Milestones: [PRD.md](PRD.md) section 11. Folder ownership: [GIT_FLOW.md](GIT_FLOW.md) section 2.

Last updated: 4 Nov 2026. Owners of future tasks follow the folder ownership; change them here when the team agrees.

## Tasks

<!-- Status: todo / doing / done / cut. Priority matches PRD (P0 / P1).
Owner: sakda1306 = api, data pipeline, RAG · Automatic28m = web, Thai UI · both = shared data/ and testing. -->

| Day | Task | Owner | Priority | Status |
|---|---|---|---|---|
| 31 Oct | Docs: PRD, Design, Contract v0.1 and v0.2, DesignSystem, conventions, git flow | sakda1306 | P0 | done |
| 31 Oct | API scaffold: app factory, Problem-JSON errors, middleware, Alembic, health | sakda1306 | P0 | done |
| 31 Oct | Auth: register, login (rate limit), logout, me, delete account (FR-26) | sakda1306 | P0 | done |
| 31 Oct | Docker Compose, `.env.example`, `.gitignore` | sakda1306 | P0 | done |
| 31 Oct | Small Apify JobThai test run and report (`jobthai_report.json`) | sakda1306 | P0 | done |
| 31 Oct | Role source PDFs, `data/roles.json`, `data/skills.json`, reference architecture notes | Automatic28m | P0 | done |
| 1 Nov | Close PRD and Design open questions (models, thresholds, Postgres, role list, embedding model, CV quota) | Automatic28m | P0 | done |
| 1 Nov | Questionnaire draft with O\*NET sources (`data/questionnaire.json`) | sakda1306 | P0 | done |
| 1 Nov | Role profiles for 26 roles (`data/roles/*.json`, `*.md`), status `draft` | Automatic28m | P0 | done |
| 1 Nov | Switch app database to Postgres (`db` container) | Automatic28m | P0 | done |
| 1 Nov | Contract v0.3 | Automatic28m | P0 | done |
| 1 Nov | Review and agree to the Contract v0.3 change-log entries (PR #23) | sakda1306 | P0 | done |
| 1 Nov | Design.md aligned with PRD (scheduled refresh, data paths, decided values) | sakda1306 | P0 | done |
| 1 Nov | Fill this schedule | sakda1306 | P0 | done |
| 1 Nov | CIBrand: Mist Slate brand with light and dark colours, fonts, logo spec and Thai tone; theme feature added to PRD and DesignSystem (FR-36 – FR-39) | Automatic28m | P0 | done |
| 1 Nov | Web scaffold: Next.js in JavaScript, Tailwind tokens (light and dark values from CIBrand), `next-themes` and theme toggle, app shell, `/api` server proxy, Dockerfile, `web` service in Compose | Automatic28m | P0 | done |
| 1 Nov | Brand assets: `logo-light.svg`, `logo-dark.svg`, `logo-mono.svg`, `mark.svg`, `favicon.ico` in `web/public/brand/` (CIBrand section 2) | Automatic28m | P0 | todo |
| 1 Nov | Web: landing, register, login pages on the auth endpoints | Automatic28m | P0 | done |
| 1 Nov | CI: GitHub Actions for api (ruff, pytest, Postgres migrations and smoke) and Docker Compose; required checks on `develop` and `main` (PR #25) | sakda1306 | P0 | done |
| 1 Nov | API: CV upload, parsing (rules only), confirm (FR-0 – FR-4) | sakda1306 | P0 | done |
| 2 Nov | API: LLM CV extraction when quota is left, on the Groq client (Design 4.1) | sakda1306 | P0 | todo |
| 1 Nov | API: quota service and `X-Quota-*` headers (FR-23, FR-24) | sakda1306 | P0 | done |
| 2 Nov | API: questionnaire endpoints serving `data/questionnaire.json`, per-question save (FR-5 – FR-7) | sakda1306 | P0 | done |
| 2 Nov | API: Groq client (two models, retry, fallback on 429/413) and AI Router skeleton (FR-11 – FR-13) | sakda1306 | P0 | done |
| 2 Nov | API: `request_log` middleware and `llm_calls` rows from the Groq client, so the admin dashboard has data from the start (Design 4.8) | sakda1306 | P0 | done |
| 2 Nov | RAG: port Team-D-II module 05 into `api/app/rag/`; Thai golden set (about 20 questions) for `multilingual-e5-base` | sakda1306 | P0 | done |
| 2 Nov | Review the 26 role profiles (reviewer other than the author); cited sources replace the Bangkok postings planned for skills marked `basis: common` | sakda1306 | P0 | done |
| 1 Nov | Data: `salary/reference.csv` from 3 salary articles (18 of 26 roles) | Automatic28m | P0 | done |
| 2 Nov | Data: `rag/work_style.md`, `rag/soft_skills.md` (status `draft`, not reviewed yet) | both | P0 | done |
| 2 Nov | Web: intake page, CV upload and parsed CV review, questionnaire tab | Automatic28m | P0 | done |
| 3 Nov | API: chat with completeness meter and `gap_question` (FR-8, FR-9, FR-14) | sakda1306 | P0 | done |
| 3 Nov | API: profile builder with cited evidence (FR-15 – FR-17) | sakda1306 | P0 | done |
| 3 Nov | API: role scoring in Python, threshold, top 5, closest roles (FR-18 – FR-20) | sakda1306 | P0 | done |
| 3 Nov | API: JobThai data provider (Bangkok only) and cache seed, one fetch per role (FR-22a, FR-22e, FR-22f) | sakda1306 | P0 | done |
| 3 Nov | Calibration with the three sample profiles (Design section 10 checks): threshold stays at 60 | both | P0 | done |
| 3 Nov | Web: chat tab and progress sidebar, profile page with skill chips and citations | Automatic28m | P0 | done |
| 4 Nov | API: next steps per gap (FR-20a); role view with salary layers, market, listings (FR-21, FR-22) | sakda1306 | P0 | done |
| 3 Nov | API: wire RAG into the api; `job_matching`, `blind_spots`, `work_style` and next steps draw on it (FR-12, FR-16, FR-20a) | sakda1306 | P0 | done |
| 4 Nov | API: profile edit by chat, skill remove and restore, recompute matches (FR-27 – FR-34) | sakda1306 | P0 | done |
| 4 Nov | API: chat answers for `skill_assessment`, `work_style`, `blind_spots`, `job_matching`, `experience`, `salary`, `market` (FR-11, FR-12) | sakda1306 | P0 | done |
| 4 Nov | API: scheduled 7-day refresh job (FR-22b, FR-22c) | sakda1306 | P0 | done |
| 4 Nov | Router evaluation set (about 40 Thai cases) for the report | sakda1306 | P0 | done |
| 4 Nov | Web: role results, role detail, edit proposal card, account page | Automatic28m | P0 | done |
| 4 Nov | API: `GET /api/admin/overview`, `ADMIN_EMAILS` check, `403 FORBIDDEN`, log cleanup (FR-40 – FR-45) | sakda1306 | P0 | done |
| 4 Nov | Web: `/admin` page with stat tiles, usage meters, share bars, cache table and warnings (FR-43, FR-44) | Automatic28m | P0 | done |
| 4 Nov | Thai copy pass and final disclaimer texts (DesignSystem section 5) | Automatic28m | P0 | done |
| 4 Nov | Check every page and state in light and dark theme, including contrast (FR-39) | Automatic28m | P0 | todo |
| 4 Nov | End-to-end test with `docker compose up --build`; bug fixes | both | P0 | todo |
| 5 Nov | Course report: scope, architecture, router accuracy, unofficial data notice, O\*NET attribution, future work | both | P0 | todo |
| 5 Nov | Tester check (5 testers, PRD section 9) and demo rehearsal on the seeded cache | both | P0 | todo |
| 5 Nov | Release: PR `develop` → `main`, final pre-push checklist, submission | sakda1306 | P0 | todo |

## Dependencies and risks this week

- **Web scaffold is done** (1 Nov afternoon: Next.js, tokens, theme toggle, `/api` proxy, Docker), but every UI page is still ahead and sits with one person. Auth pages next; drop P1 UI items first (cut list).
- **API has only auth and health.** CV, questionnaire, chat, profile, roles and quota endpoints are all ahead, with the heaviest load on 3–4 Nov.
- **Contract v0.3** waits for sakda1306 to agree. Web codes against the new fields (`max_choices`, `career_stage`, `location_scope`, kebab-case ids), so agree on 1 Nov.
- **CIBrand** is done (Mist Slate, light and dark), so tokens can be final from the scaffold. Two themes mean every page is checked twice; build components on tokens only so the dark theme needs no extra code.
- **Role profiles** are all `status: reviewed` (reviewer sakda1306, 3 Nov). Every required skill cites a source, but most new sources are not about the Thai market, 94 of 170 kept their earlier evidence without a new check, 20 have weak evidence, and `nice_to_have` and `soft_skills` were not checked. State these limits in the report.
- **RAG port and role profiles** (2 Nov) block scoring, next steps and evidence (3 Nov).
- **Apify credits**: the seed and the weekly refresh are 26 runs and about 520 results per week (PRD FR-22c). Check `jobthai_report.json` before changing the role count.
- **Groq limits**: use a separate Groq account for the demo so testing does not use up its daily tokens (Design section 4.7). Check the admin dashboard before every rehearsal.
- **Admin dashboard** adds an endpoint and a page on 4 Nov, the busiest day. The logging (2 Nov) must land first, or the panels will be empty; Contract v0.3d needs sakda1306's agreement before then.

## Cut list

Drop in this order if behind schedule:

1. Quota indicator in the UI (FR-25, P1).
2. Streaming chat responses (FR-10, P1).
3. LLM-assisted CV extraction; keep rules-only parsing, which is the decided fallback (Design section 4.1).
4. Scheduled refresh job; the seeded cache stays the baseline for the demo (FR-22a).

## Done log

- 31 Oct 2026: docs set, API scaffold with auth, Docker Compose, Contract v0.2, JobThai test run, role sources and data lists (PR #1–#8).
- 1 Nov 2026: open questions closed, questionnaire, 26 role profiles (draft), Postgres, Contract v0.3, Design aligned with PRD (PR #10–#14).
- 4 Nov 2026: web pages done (landing, auth, intake, chat, profile, roles, account, admin); Thai copy pass: one skill level scale (เริ่มต้น / ใช้งานได้ / คล่อง / เชี่ยวชาญ), one word for quota reset (รีเซ็ต) and skill restore (กู้คืน), threshold text from one constant.
