# 04 — AI / LLM

> Paths are relative to `DL-07-Agentic-AI-System-II/`.

## Headline fact

**No live LLM is called anywhere in this codebase.** No LLM SDK is imported (no `openai`, `groq`, `langchain`). The patterns worth copying are the **seam, the guardrails and the fallback**, not a client.

| Place an LLM was planned | What the code does instead | File |
|---|---|---|
| 03 intent + planner | Rule-based: intent hint from 02 + fixed tool order; `prompt_version = "rules-v1"` | `03_travel_ai_agent/travel_agent/config.py:9-10`, `travel_agent/pipeline.py:254-279` |
| 07 explanation | `ExplanationProvider` Protocol; `app.state.provider = None` ⇒ always template | `07_decision_llm_engine/decision_engine/explanation.py:31-32`, `decision_engine/api.py:27` |

## LLM client wrapper (07 seam)

```python
class ExplanationProvider(Protocol):
    async def generate(self, package: dict, *, max_output_tokens: int) -> dict: ...
```
`decision_engine/explanation.py:31-32`. Wired in `decision_engine/service.py:21` and `:33-35`. A real provider (e.g. a Groq client) would implement this one method.

## Model config (07)

| Setting | Default | Guard | File |
|---|---|---|---|
| `LLM_MODEL_EXPLAINER` | `"disabled"` | — | `decision_engine/config.py:15` |
| `LLM_API_KEY` | empty `SecretStr` | never logged | `config.py:14` |
| `TEMPERATURE` | 0 | `ge=0, le=0` (forced to 0) | `config.py:16` |
| `MAX_INPUT_TOKENS` / `MAX_OUTPUT_TOKENS` | 8000 / 1500 | bounded | `config.py:17-18` |
| `LLM_TIMEOUT` | 3 s | `le=60` | `config.py:19` |
| `LLM_MAX_ATTEMPTS` | 2 | `le=3` | `config.py:20` |
| `PROMPT_VERSION` | `"v1"` | only `v1` accepted | `config.py:34-39` |
| `DECISION_POLICY_VERSION` | `prototype-v3` | only bundled version accepted | `config.py:27-32` |
| `POLICY_APPROVED` | False | env var cannot set it to True | `config.py:41-46` |
| `ESCALATION_RULES` | fixed set of 8 flags | changing requires new reviewed policy | `config.py:55-70` |

Model name in responses: `settings.llm_model_explainer` if provider used, else `"template-v1"` (`decision_engine/service.py:72`). Versions also travel to 02 and are stored per recommendation (`agent_version`, `risk_model_version`, `prompt_version`) (`02_api_backend/app/infrastructure/db/models/recommendation.py:95-98`).

## Prompts

Only one prompt exists, built as a JSON package (`decision_engine/explanation.py:63-72`):

> `"system": "Explain the locked action using only the supplied sentence bank. Never change its meaning, numbers, instructions or evidence IDs."`

Package fields: `locked_action`, `prompt_version`, `temperature`, `sentence_bank` (the template output), `evidence_ids`, `output_schema` (Pydantic JSON schema of `Candidate`).

User-facing text comes from versioned templates, Thai and English: `decision_engine/templates/v1.json` (summaries per action, reasons per rule id, instruction, review instruction, uncertainty). Rendered with Jinja `StrictUndefined` + autoescape; comment: "Only trusted, versioned template text enters Jinja. Never render RAG excerpts." (`explanation.py:38-39`).

## Structured output, validation, token counting

| Concern | Implementation | File |
|---|---|---|
| Output schema | `Candidate(BaseModel)` with `extra="forbid"`, length caps | `explanation.py:14-28` |
| JSON parsing | `Candidate.model_validate(raw)` | `explanation.py:90` |
| Grounding check | Candidate must equal the template exactly: same `action_code`, same summary, same sets of reasons/instructions/uncertainty, same evidence ids | `explanation.py:91-98` |
| Input budget | **UTF-8 byte length** of the package used as an upper bound for tokens; over budget ⇒ template. Comment says to replace with provider's tokenizer | `explanation.py:73-77` |
| Output budget | byte length of returned JSON vs `max_output_tokens` | `explanation.py:87-89` |
| Retries | loop of `llm_max_attempts`, all inside one `asyncio.timeout(llm_timeout)` | `explanation.py:80-119` |
| Error logging | provider exceptions not logged ("can contain API keys or prompt text") | `explanation.py:109-111` |
| Result flags | `LLM_DISABLED_TEMPLATE_USED`, `LLM_INPUT_BUDGET_TEMPLATE_USED`, `LLM_OUTPUT_BUDGET`, `LLM_UNGROUNDED_OUTPUT`, `LLM_PROVIDER_OR_SCHEMA_ERROR`, `LLM_TIMEOUT`, `LLM_OUTPUT_VALIDATED`, `LLM_INVALID_OR_UNAVAILABLE_TEMPLATE_USED` | `explanation.py:61-122` |
| Degraded flag | template mode ⇒ `degraded_services=["llm"]` | `decision_engine/service.py:58` |
| Audit | JSONL per decision: rules fired, evidence ids, versions, confidence, explanation mode, validation results | `decision_engine/audit.py:28-48` |

Note: the grounding check in `explanation.py:91-98` is so strict that the LLM can only reorder lists. The docstring says so: "This deliberately restrictive prototype cannot invent a number, citation or emergency instruction" (`explanation.py:15-20`).

## Routing / decision (deterministic, LLM-free)

### 07 decision table: first matching rule wins

`decision_engine/policies/prototype-v3.json` rules in order:

| Rule id | Action |
|---|---|
| OFFICIAL_RESTRICTION | AVOID |
| HIGH_RISK | AVOID |
| NO_SAFE_ROUTE | AVOID |
| INSUFFICIENT_EVIDENCE | AVOID |
| SAFER_ROUTE | CHANGE_ROUTE |
| SAFER_TIME | DELAY |
| LOW_RISK_CLEAR | NORMAL |
| UNRESOLVED | AVOID |

Conditions computed as booleans in `decision_engine/policy.py:171-183`; loop `policy.py:184-192`. Confidence: ordinal map `LOW 0.25 / MEDIUM 0.65 / HIGH 0.9`, escalation below 0.5, capped by issues/conflicts (`prototype-v3.json` `confidence`, `policy.py:49-83`).

### 03 tool routing

Fixed allowlist (`03_travel_ai_agent/travel_agent/tools/base.py:27-38`), fixed order (`pipeline.py:122-140`). No dynamic tool selection.

### 02 intent hint

`IntentHint` enum `PLAN_TRIP | CHECK_SAFETY | ASK_INFO | FOLLOW_UP` (`02_api_backend/app/infrastructure/agent/contracts.py:36-40`); only `FOLLOW_UP` / `CHECK_SAFETY` are used (`02_api_backend/app/services/agent_run_service.py:379`).

## Hallucination / invalid output handling (defence in depth)

| Layer | Guard | File |
|---|---|---|
| 07 | LLM cannot change the action; text must match the sentence bank; fallback to template | `explanation.py:91-122` |
| 07 | Missing/stale/conflicting evidence ⇒ `INSUFFICIENT_EVIDENCE` ⇒ AVOID + escalation | `policy.py:175`, `prototype-v3.json` |
| 06 | Retrieval returns empty instead of generic text; "No generic emergency procedure is fabricated" | `06_risk_knowledge_services/risk_knowledge/knowledge.py:73-77` |
| 04 | Provider failure ⇒ explicit `unavailable` record, never fake values | `04_external_data_services/weather_service.py:32-66`, `open_meteo_adapter.py:37` |
| 03 | Tool failure ⇒ service `UNAVAILABLE`, run continues as partial | `03_travel_ai_agent/travel_agent/pipeline.py:208-241` |
| 02 | Agent body validated against Pydantic contract; bad schema ⇒ `AGENT_BAD_RESPONSE` | `02_api_backend/app/infrastructure/agent/client.py:384-393`, `contracts.py` |
| 02 | Safety Gate: R-02 no fresh weather/disaster ⇒ cannot say "safe"; R-03 degraded ⇒ partial; R-01 HIGH needs emergency instructions (DB fallback by region/language); R-04 HIGH + TRAVEL_NORMALLY ⇒ reject + safety review; R-05 contract violations ⇒ reject | `02_api_backend/app/domain/safety_gate.py:131-202`, `app/services/agent_run_service.py:413-426` |
| 02 | Low-confidence warning below 0.5 | `app/core/config.py:386` |
| 02 | Output sanitizer: strip control chars, safe URLs, drop internal keys | `app/domain/sanitizer.py:20-65` |
| 02 tests | Mock agent `bad_schema`, `partial_disaster_down` scenarios prove gate catches bad output | `02_api_backend/mock_agent/scenarios/*.json` |

## Mapping to CareerMirror

- CareerMirror's "LLM only explains the score" = this repo's "locked action + sentence bank" pattern. Copy `ExplanationProvider` + `Candidate` + fallback loop; **relax** the exact-match check to: same score/role ids, cited ids ⊆ supplied ids, numbers in text ⊆ numbers in input.
- AI Router (exactly one route): **Not found in code** as an LLM classifier. Closest reusable shape: a `StrEnum` intent (`contracts.py:36-40`) + allowlisted handlers (`tools/base.py:27-38`) + "ask instead of guess" clarification (`pipeline.py:254-279`).
- Token counting: replace byte-length proxy with the Groq tokenizer or a char/3 heuristic for Thai.
