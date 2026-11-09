# CareerMirror API

FastAPI backend. Endpoints and error codes: [docs/Contract.md](../docs/Contract.md). Architecture and code layout: [docs/Design.md](../docs/Design.md).

## Run locally (without Docker)

```bash
cd api
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env           # then set JWT_SECRET (32+ characters) and DATABASE_URL
                                  # (needs a running Postgres, e.g. a local install)
mkdir -p var                      # RAG SQLite file and index snapshot
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive API docs.

## Run with Docker

From the repo root: copy `.env.example` to `.env`, set `JWT_SECRET` and `POSTGRES_PASSWORD`, then `docker compose up --build`. App data lives in Postgres (`db` service, `db-data` volume); the RAG SQLite file and index snapshot live on the `api-data` volume; `/data` is mounted read-only.

## Tests and lint

Tests use a temporary SQLite file, so they need no Postgres.

```bash
pytest -q
ruff check . && ruff format --check .
```

## Database changes

Edit `app/infra/models.py`, then add a migration in `migrations/versions/` (next number, e.g. `0002_cv_documents.py`). New user tables need `ForeignKey("users.id", ondelete="CASCADE")` so `DELETE /api/me` removes them. `alembic check` must report no differences.

## What exists so far

| area | status |
|---|---|
| app factory, Problem-JSON errors, request id, security headers, body limits | done |
| auth: register, login (5 failures/min per email), logout, me, delete account | done |
| health | done |
| quota service, `GET /api/quota` | done |
| CV: upload, rules-only parsing, confirm, delete | done (LLM extraction not started) |
| questionnaire: questions, per-question save, completeness | done |
| Groq client (`app/infra/llm.py`): models per task, retry, fallback | done |
| AI Router (`app/router/`, `services/router_service.py`): guards, rules, LLM decision, quota, `router_log` | done (no endpoint calls it until `POST /api/chat`) |
| `request_log` and `llm_calls` rows | done |
| RAG (`app/rag/`): chunks from `/data`, BM25 + FAISS + RRF, filters by role and category | done (no endpoint calls it until `POST /api/chat`) |
| `POST /api/chat`, `GET /api/chat/history`, `GET /api/profile/completeness`: `gap_question`, `clarify` and `decline` answer; other routes reply "not ready" until their handlers exist | done |
| `POST /api/profile/generate`, `GET /api/profile` | done |
| `GET /api/roles`, `GET /api/roles/matches`, `GET /api/roles/{role_id}`: scores and gaps; `reason_th` and `next_steps` stay empty until the explain step | done |
| profile edits, `POST /api/roles/matches/explain` | not started |
| quota headers `X-Quota-*` on authenticated responses | done |
