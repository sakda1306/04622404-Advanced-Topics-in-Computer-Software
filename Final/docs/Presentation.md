# CareerMirror: what to present (Friday)

The teacher's focus: how AI is brought into the web app, the techniques, the problems, the evaluation, and which features use AI and which do not.

Main message: **AI only where language is needed. Numbers and decisions are computed in Python, and every claim cites its evidence.**

Status: **ready** = the number is in the repo; **measure** = still to collect before Friday.

---

## 1. Problem and goal

| Data | Source | Status |
|---|---|---|
| The problem: people do not know which IT role fits their skills; asking an LLM to score you gives inconsistent, uncheckable results | PRD.md §2 | ready |
| What the app does: CV, questionnaire and chat → evidence-backed profile → match against 26 IT roles → gaps, next steps, salary and Bangkok market data | PRD.md, Design.md §1 | ready |
| Scope: IT roles only, Bangkok job data, Thai UI | CONVENTIONS.md (MVP scope) | ready |

## 2. How AI is brought into the web app (architecture)

| Data | Source | Status |
|---|---|---|
| Three containers: `web` (Next.js), `api` (FastAPI), `db` (Postgres); router, retrieval and LLM calls all inside `api` | Design.md §1–2 | ready |
| One request path: web → API → AI Router → RAG / external data / Python scoring → LLM writes the wording → evidence check → response | Design.md §3 | ready |
| LLM provider and models: Groq; `openai/gpt-oss-120b` for user-facing Thai text, `qwen/qwen3.8-27b` for structured tasks and as fallback; model ids in env | Design.md §4.7 | ready |
| Limits that shaped the design: 30 req/min, 1,000 req/day, 8,000 tokens/min, 200,000 tokens/day per model; per-user quota 40 requests and 40,000 tokens a day | Design.md §4.7 | ready |

## 3. Which features use AI and which do not

| Feature | AI? | Technique |
|---|---|---|
| Chat routing | Partly | Guards → keyword rules (no LLM) → LLM classifier (structured output) → `clarify` below 0.6 confidence |
| Facts from chat answers | LLM | Structured JSON; Python checks each skill appears in the message |
| Profile: experience summary, blind spots | LLM | Writes from given facts only; each claim must cite evidence ids |
| Match reasons and next steps | LLM + RAG | Learning-path chunk from RAG; one action per computed gap |
| Chat answers about skills and blind spots | LLM + RAG | Claims checked by `parse_claims`; computed text if none hold up |
| Profile edits through chat | LLM | Request → structured change; the user must confirm; the LLM never writes to the profile |
| Knowledge search | RAG | BM25 (pythainlp) + FAISS (`multilingual-e5-base`), fused with RRF k = 60 |
| CV reading | Rules first, LLM optional | Rules + skill taxonomy; LLM extraction only if quota is left; the user confirms |
| **Match %** | **No** | Python: 0.70 required skills, 0.15 nice-to-have, 0.10 soft skills, 0.05 work style |
| Skill levels, experience months, completeness | No | Python rules |
| Salary and market answers | No | Reference table and cached JobThai data; the LLM writes nothing |
| Work-style character, dashboards, quota | No | Plain code |

Source: Design.md §4.1–4.6, §9. Status: ready.

## 4. Techniques

| Technique | Data to show | Source | Status |
|---|---|---|---|
| AI Router (4 layers, cheap first) | Layer order; an LLM routing call uses about 260 tokens; share of messages decided by rules vs LLM vs guard | Design.md §4.6; admin dashboard (AI Router tile) | ready; router shares: read from the dashboard after a real run |
| Hybrid RAG | Why hybrid: BM25 catches exact skill names, vectors catch meaning; corpus = 26 role files + 2 notes, chunked at headings, filtered by role and category | Design.md §6 | ready |
| Hallucination control | Facts carry evidence ids; `parse_claims` drops claims with no valid id or with numbers not in the facts; citations [n] shown to the user | Design.md §4.2–4.3 | ready |
| Share of LLM claims dropped by `parse_claims` | One number from a real profile generation | logs or a small script | **measure** |
| Two-model strategy | Large model for Thai text users read; small model for structured tasks and fallback; separate daily token pools | Design.md §4.7, §9 | ready |
| Reliability | Retry → fallback model → Thai error; router calls time out at 7 s and retry; quota checked before every LLM call | Design.md §4.7 | ready |
| Design decisions and trade-offs | Match % in Python, not LLM; role profiles, not postings; hybrid search inside the API, not a separate vector DB; user confirms edits | Design.md §9 | ready |

## 5. Evaluation

| What | Data | Result | Source | Status |
|---|---|---|---|---|
| Router accuracy | 2 held-out Thai sets, 34 cases each | 91% (first set) → 97% (second set, after a rule fix); LLM layer 26/26; all errors from keyword rules | Design.md §4.6 (router evaluation) | ready |
| RAG retrieval | Thai golden set, 30 questions | Hybrid hit@1 0.70, hit@3 0.93; vector hit@3 0.90; BM25 hit@3 0.83; passed the 0.8 bar, so e5-base kept over bge-m3 | Design.md §6 | ready |
| Match calibration | 3 sample profiles (student, full-stack, ML) | Own role in top 3 and ≥ 60; unrelated roles under 30; student sees 1 role at threshold 60 | Design.md §10, `api/tests/test_roles.py` | ready |
| End-to-end API | `e2e/e2e_api.py`, groups A–F | 78 passed, 0 failed (4 Nov) | `e2e/runs/` | ready |
| Unit and integration tests | pytest | 976 passed | `api/tests` | ready |
| Cost | Full e2e run | 6/40 requests, 6,861/40,000 tokens | `e2e/runs/` | ready |
| Speed | LLM latency p50 / p95 (target ≤ 15 s); examples: skill chat 1.2 s, off-topic refusal 0.3 s | admin dashboard; `e2e/runs/` | p50/p95: **measure** |
| Limits of the evaluation | Small sets written by the team; tuned set (47 cases) kept apart from held-out sets; no user study; LLM explanations not rated yet | Design.md §4.6 | ready |

Re-run `api/tests/router/eval_routes.py` and `api/tests/rag/eval_golden.py` on the final build so the numbers carry a fresh date.

## 6. Problems and how they were solved

| Problem | What was found | Fix | Source |
|---|---|---|---|
| Embeddings could not map free-text skills | e5 gave "ทำอาหาร" 0.83 and "ReactJS → React" 0.84; no threshold separates them | Alias taxonomy; unknown skills stay in the user's words | Design.md §4.2 |
| Groq rate limit (8K tokens/min) | 429 during tests; 10 edits in a row were throttled | Retry, fallback model, per-user quota, prompts under 5K tokens | Design.md §4.6–4.7 |
| LLM timeouts (~1% of 380 calls) | Random `ReadTimeout` | Short per-attempt timeout and an immediate retry for router calls | Design.md §4.6 |
| Made-up claims and numbers | LLM sentences without evidence | Evidence-id and number check in `parse_claims` | Design.md §4.2 |
| Unofficial job data (Apify, 20 per run) | Cannot depend on it live | Shared per-role cache, weekly refresh, date and source shown | Design.md §4.4, §7 |
| Scanned PDFs | No text layer | Thai error message; the questionnaire still works | Design.md §4.1 |
| Student profile sees 1 role at threshold 60 | Calibration check failed | Kept 60; closest roles shown with what to add | Design.md §10 |
| Experience months wrong after editing the CV form | Months came only from the first parse | Recalculated from the dates on save (#58) | `api/app/services/cv_service.py` |

## 7. Demo (what to show)

1. Upload a CV → confirm the parsed fields (rules first, user corrects)
2. Generate the profile (the animation shows the real request stages)
3. Profile: click a citation [n] to show its evidence
4. Role matches: match % from Python; reason and next steps from the LLM
5. Chat: salary (no LLM) · skill question (LLM + RAG with citations) · off-topic (guard refuses) · "เปลี่ยนระดับ SQL เป็น 3" (edit proposal → confirm)
6. Admin dashboard: router layer shares, LLM usage per model, error rate, latency

Prepare: a demo account with a CV, a separate Groq key for the demo, the market cache seeded (`api/scripts/seed_market.py`, spends Apify credits), a recorded backup video.

## 8. Limits and future work

- Small evaluation sets; no user study
- IT roles and Bangkok data only; job data source is unofficial
- One LLM provider
- Future: larger held-out router set, human or LLM-as-judge rating of explanations, user testing, more roles

## Before Friday

- [ ] Measure the share of claims dropped by `parse_claims` (section 4)
- [ ] Read LLM latency p50 / p95 and router layer shares from the admin dashboard after a real run (sections 4–5)
- [ ] Re-run the router and RAG evaluations on the final build
- [ ] Seed the market cache for the demo
- [ ] Use a separate Groq key for the demo
- [ ] Record a backup demo video
