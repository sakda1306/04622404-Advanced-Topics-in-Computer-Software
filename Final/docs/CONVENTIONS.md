# CareerMirror: Conventions

Status: updated 1 Nov 2026 to match the decided PRD, Design and Contract. Details and reasons live there; this file is the short version.

Project rules, stack, architecture summary, conventions and commands for everyone working in this repo. Scope is in [PRD.md](PRD.md).

## Project

AI Router + RAG web app for a course final project (Advanced Topics in Computer Software, RMUTT).
Goal: help a user understand themselves for job applications. The user gives a CV (PDF), a questionnaire and a chat; the app builds a profile (hard/soft skills, work-style preferences, experience, blind spots) and then shows job match %, next steps / gap to close, salary range and market demand, each with reasons.

Positioning: self-understanding first, job matching as the payoff. Not a job board.

Timeline: start 31 Oct 2026, deadline 5 Nov 2026 (about 6 days). Scope must stay at MVP.

## Tech stack

- Frontend: Next.js 16 (App Router) with React 19 and Tailwind CSS 4, in JavaScript, not TypeScript (decided 1 Nov 2026); `.js` / `.jsx` files, Thai UI, `next-themes`, Lucide icons
- Backend: Python 3.12, FastAPI (decided 31 Oct 2026)
- Auth: email and password login (decided 31 Oct 2026)
- LLM: Groq API (decided 1 Nov 2026): `openai/gpt-oss-120b` for user-facing text, `qwen/qwen3.8-27b` for the router, extraction and as fallback ([Design.md](Design.md) section 4.7). Model ids live in env vars (`GROQ_MODEL`, `GROQ_ROUTER_MODEL`, `GROQ_FALLBACK_MODEL`), never hardcoded
- RAG: hybrid search inside the api, ported from Team-D-II `services/05_retrieval_knowledge` (decided 31 Oct 2026). The index lives in memory, so the api runs as **one uvicorn worker** ([Design.md](Design.md) section 8). Embedding model `intfloat/multilingual-e5-base` (decided 1 Nov 2026), with `BAAI/bge-m3` as the fallback if the Thai golden set scores below 0.8 hit@3
- Storage: Postgres for users, profiles, quota counters and the job cache (decided 1 Nov 2026); the RAG retrieval store stays a SQLite file inside the api
- Infra: Docker Compose runs three containers: `web` (port 3000), `api` and `db` (Postgres)

Details and reasons: [Design.md](Design.md).

## Architecture

Web App -> API/Backend -> AI Router -> (RAG | External data | local scoring) -> Profile Builder -> LLM -> report

- AI Router picks one route per request: skill assessment, work style, blind spots, job matching (with next steps), salary, market, experience, profile edit; before a profile exists, chat mostly asks gap questions.
- Skill-match scores are computed in plain Python; the LLM only explains the result (cheaper, consistent).
- Profile Builder checks completeness (CV, questionnaire, chat) and exposes a 0-100% meter. "Generate profile" is a user action, not automatic.
- Per-user daily request/token limit is enforced in the backend before any LLM call.
- Every API request and every LLM call is logged without content (`request_log`, `llm_calls`); a read-only admin dashboard shows the aggregates (PRD 6.12).
- Next steps / gap to close: per match, the scoring step already knows missing skills; the LLM turns them into prioritised actions (skills to learn, CV edits), each tied to a gap.
- Role-level matching (decided): the match is profile vs. a fixed list of 26 IT role profiles, not vs. individual job postings.
  - Each role profile is structured data in `data/roles/<role_id>.json` with prose in `data/roles/<role_id>.md`: required and nice-to-have hard skills (weighted), soft skills, work-style traits, plus a prose description and learning-path text for RAG. Record who wrote each profile and its sources.
  - Match % is computed in Python from skill overlap (hard skills dominate; work-style has a low weight). Embeddings only map free-text skills to the skill taxonomy and retrieve explanation text; they never produce the match %.
  - Only roles above a calibrated threshold are shown, each with evidence and gaps. If none pass, show the closest roles and what is missing. Calibrate the threshold with sample profiles (student, full-stack dev, ML dev).
  - The user picks a role to see its salary, demand and real listings.
- External data (decided 1 Nov 2026): salary and market come from real Thai sources behind a single `data provider` interface in the backend.
  - Cache is keyed by role, shared across all users (never fetched per user), with `fetched_at`. Seed it before the demo with one fetch per role; this is the guaranteed baseline.
  - Fetch Bangkok jobs only (location filter in the request, plus a location check at ingest).
  - A scheduled job refreshes every role once every 7 days, up to 20 postings per role (26 roles: about 104-130 runs a month). User actions never trigger a fetch. Never block the report on the API; on failure keep the cached data labelled with its date. See PRD FR-22a to FR-22f.
  - Reading a clicked role always uses the cache. Show "last updated" and a loading state while a refresh runs.
  - Salary is shown in two layers, always with source, measure (monthly base vs. annual total compensation) and date: (1) ranges advertised in postings, parsed from text; (2) a hand-curated reference table in `/data` (source, URL, retrieved date per role; check each site's terms), with the NSO IT-industry wage as a sanity check.
  - Official, free: NSO / data.go.th wage datasets (by industry, region, education; not by job title; check the latest year).
  - Unofficial (decided 1 Nov 2026: JobThai only): Apify JobThai scraper (mai_amm/jobthai-scraper: `jobTypes` 7 = Computer/IT, `includeDetails` on, leave `includeContacts` off; free plan caps 20 jobs per run; salary is a text string to parse). Pay per result. The team does not review the site's terms (accepted risk); say in the report that the source is unofficial and its terms were not reviewed.
  - Not used: JobsDB scraper and Techmap API (free tier 100 requests/month, Thailand coverage unverified). Levels.fyi API is sales-gated; Greenhouse and Upwork are not useful here; no official Thai job-board API was found.
  - Filter all job data to the IT role list at ingest.

## MVP scope

In: CV upload and parsing, questionnaire (skills + work-style preferences), chat with progress sidebar, generated profile, role-level match % (above threshold only) with reasons, next steps / gap to close per role, role pick, salary range and market summary from real Thai data (cached per role, scheduled weekly refresh), quota limit, account deletion, light and dark theme, read-only admin dashboard for the team (`ADMIN_EMAILS`).
Job domain: computer/IT jobs only, e.g. AI Engineer, Software Engineer, Full-stack Developer, and related roles (backend, frontend, data, ML, DevOps, QA). Other fields are out of scope; the seed/scraped data, skill taxonomy and RAG documents are limited to this domain.
Out (future work, mention in report): non-IT jobs, job tracker, interview prep, profile versioning, full PDPA tooling, a sanctioned live job-board partnership.

## Conventions

- All user-facing text is Thai. Code, comments, commit messages and docs are English.
- Every match % and claim in the profile must cite evidence (CV line, questionnaire answer, or RAG source). No unexplained numbers.
- No MBTI. Work-style preferences (e.g. teamwork vs. solo, structure vs. ambiguity) are self-reported preferences, not personality diagnoses; show them as such.
- Secrets (GROQ_API_KEY etc.) live in `.env`; commit only `.env.example`.
- Do not send more personal data to the LLM than the route needs.
- Keep the frontend/backend contract in `docs/Contract.md`; change it only with both members agreeing.

## Git rules

Branches, ownership, commit format and the pre-push checklist are in [GIT_FLOW.md](GIT_FLOW.md). The rules that are never broken:

Do not add tool attribution or automated authorship trailers. Review outgoing files before every push.
- Personal tool folders stay out of git through `.git/info/exclude`, never through the shared `.gitignore`.
- Run the pre-push checklist ([GIT_FLOW.md](GIT_FLOW.md) section 4.1) before every push: secrets, stray files, commit authors and trailers.
- Changes reach `develop` and `main` only through reviewed PRs.

## Layout

```
/web                    Next.js app; layout and token rules in web/README.md
/api                    FastAPI app; code layout in Design.md section 2.1
/data
  roles.json            the 26 roles (id, Thai/English name, sources)
  roles/<role_id>.json  role profile used for matching
  roles/<role_id>.md    role description and learning path (RAG source)
  skills.json           skill taxonomy (ids, Thai/English names, aliases)
  questionnaire.json    the 22 questions, with O*NET sources
  role-skills.draft.json  superseded draft, kept as the record of skill sources
  salary/reference.csv  curated salary ranges per role (sources and rules in salary/README.md)
/pdf                    source documents cited by the role profiles and the salary table
/docs                   PRD, Design, DesignSystem, CIBrand, Contract, Schedule, GIT_FLOW
  brand/                brand book PDF (visual companion to CIBrand.md)
/reference-architecture another project, kept as background reference only
docker-compose.yml
```

## Commands

- Run all: copy `.env.example` to `.env`, set `JWT_SECRET` (32+ characters) and `POSTGRES_PASSWORD`, then `docker compose up --build`. The api runs `alembic upgrade head` on start.
- API dev without Docker: needs a Postgres reachable at the `DATABASE_URL` in `.env`; then `cd api && alembic upgrade head && uvicorn app.main:app --reload --port 8000` (setup steps in `api/README.md`).
- Tests: `cd api && pytest -q`. Tests use a temporary SQLite file, so no Postgres is needed.
- Lint: `cd api && ruff check . && ruff format --check .`
- Web dev: `cd web && npm install && npm run dev` (http://localhost:3000; the `/api` proxy uses `API_BASE_URL`, default `http://localhost:8000`); lint: `npm run lint`; build: `npm run build`.

## Files kept in docs/

- `PRD.md`: requirements, source of truth for scope.
- `Design.md`: architecture and flow only (there is no separate architecture.md).
- `DesignSystem.md`: all UI rules; colours and fonts are referenced from `CIBrand.md`.
- `CIBrand.md`: brand identity, the only place colour and font values are defined.
- `brand/CareerMirror_BrandBook_MistSlate.pdf`: the brand book, the visual reference every design follows; its values come from `CIBrand.md`.
- `Contract.md`: frontend/backend API contract.
- `Schedule.md`: day-by-day task plan.
- `GIT_FLOW.md`: branches, ownership, commits, PRs, pre-push checklist.
- `jobthai_report.json`: result of the 31 Oct Apify JobThai test run (salary coverage, cost, budget for 26 roles).
- `CONVENTIONS.md`: this file.

Link between them instead of copying text.
