# 03 AI Router Agent

FastAPI router for the Premier League Football Assistant. It implements `docs/CONTRACT.md` §2–5 without changing neighboring services.

## Routes

`POST /route` selects `football_rag`, `general_ai`, `local_ai`, `clarify`, or `decline`. Decisions run through guards, rules, the `/local/classify` engine (score at least 0.75), and finally a structured LLM decision. The LLM uses Groq first and Gemini once as a fallback. Rule decisions report confidence `0.9`; classifier and LLM decisions report their own score.

The router maps team names and Thai nicknames to football-data.org team IDs, resolves simple follow-ups using the latest classifiable user message, and turns relative dates into search filters. It refreshes the team list from 07 every five minutes and keeps the offline list if 07 returns invalid team data. `data/team_aliases.json` supplies the initial and offline list. Each LLM provider gets up to three seconds so Gemini can be tried if Groq stalls within the eight-second decision budget.

For factual answers it searches 05 and passes the retrieved contexts to 06. Thai search rewrites keep the entire original question alongside English search hints so names and conditions reach 05. An empty filtered search is retried once without temporal filters, except when a standings question explicitly names a matchweek; that search returns empty rather than substituting the current table. Trivia can fall back to General AI with an explicit caveat; match results, fixtures, standings, and weekly reports never do. General and local engine drafts pass through 06. A 501 prediction response becomes the contracted unavailable message. Every response includes route confidence, trace, latency, and token usage.

## Run

From this directory:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `RETRIEVAL_URL`, `ENGINES_URL`, `GENERATION_URL`, and `FOOTBALL_DATA_URL` when the services do not use the Compose hostnames (`http://retrieval:8000`, `http://engines:8000`, `http://generation:8000`, `http://football-data:8000`). To enable the LLM decision layer, set `GROQ_API_KEY` and `GROQ_MODEL`; optionally set `GEMINI_API_KEY` and `GEMINI_MODEL` for fallback. No key is required for guard and rule decisions.

Run the offline tests with `python -m unittest discover -s tests -v`. Run `python eval_routes.py` for the measured 44-case router evaluation (including a team trivia question). It prints `total`, `correct`, `route_accuracy`, and failures; a mismatch exits with code 1. This benchmark uses deterministic replies for 04/05/06, so its accuracy measures routing of these examples, not live answer quality. The test suite also covers HTTP request and response shapes with mocked upstream services, source forwarding, 503 prediction, 503 retrieval, and router timeout.

## Integration checkpoints

- 02 calls `POST /route` at the router service URL and sends `X-Request-ID`.
- 04 provides `/general`, `/local/classify`, and optionally `/local/predict` at the configured Engines URL.
- 05 provides `/search` at the Retrieval URL.
- 06 provides `/generate` at the Generation URL.
- 07 provides `/football/teams`; the local alias list is used while 07 is unavailable.
- 02 now includes optional `context.last_ingest_at` from 07 status. For an empty live-data search, 03 shows that timestamp when present and does not invent one when 07 status is unavailable or the field is null.
- Scorer questions in Thai or English use the `standings` category required by `docs/CONTRACT.md` §4. When the user omits a matchweek, 03 filters to `context.current_matchweek` first, then retries without that filter if 05 returns no chunks. A factual scorer answer still depends on 07 publishing scorer data in the indexed standings document and 05 returning it; the retry cannot guarantee the newest document ranks first.
- Prediction questions (CONTRACT v1.7) no longer call 04 directly. Two teams → 07 `GET /football/predict`; title / top-4 / relegation outlook → 07 `GET /football/simulation`; anything else asks which match or season view. The draft is written from the numbers (`app/prediction_text.py`) with a statistical-estimate disclaimer and goes to 06 passthrough. If 07 or 04 is down the answer is "ตอนนี้ระบบทำนายผลไม่พร้อมใช้งาน" (`trace.fallback = "simulation_down"`), never `general_ai`.
- Trivia searches use the `trivia` category without a team or time filter because the indexed trivia documents have no team IDs. Team names remain in the rewritten search text.
- Historical top-scorer questions with an explicit season start year use 07's curated Premier League reference directly. A bare year such as `2025` is interpreted as season `2025/26` and labeled as an assumption in the answer. Unsupported years return no ranking, while current-season questions continue through indexed standings. This covers verified scorer winners only; the full historical index remains separate.

The deploy owner supplies the service container and Compose wiring. This module contains only the router implementation and its own tests.

## Verification scope

The router unit tests and 44-case route evaluation use simulated upstream responses. The 02-to-03 context handoff was also checked with the current 02 `router_context` function and `RouteContext` schema feeding the actual 03 `/route` ASGI endpoint: an empty search included the supplied `last_ingest_at` in the fallback answer; unavailable 07 status produced a null timestamp and no claimed update time. This check used a simulated empty 05 response and did not run the full 02 HTTP server.

Live answer quality, citations from the indexed data, scorer coverage, and the complete 03→04/05/06/07 path still require the corresponding services and data to run together. The 44-case route score does not establish those results.
