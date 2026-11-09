# CareerMirror Golden Dataset v1

100 Thai evaluation candidates for the CareerMirror knowledge and conversation features.
This is an internal benchmark draft, pending independent human review. It is not an
externally certified standard, a representative sample of real traffic, or a full
application acceptance suite. No production user data is included.

## Files and coverage

| File | Purpose |
| --- | --- |
| `golden_th.jsonl` | Authoritative set of 100 cases |
| `review.md` | Readable questions, reference answers, fixtures, and review criteria |
| `retrieval_th.jsonl` | Exact export of the 80 retrieval cases; not another 80 cases |
| `manifest.json` | Version, review state, source hashes, dataset hash, proposed target |
| `benchmark.py` | Offline validation, prediction scoring, production retrieval runner |
| `test_benchmark.py` | Checks for metric denominators and invalid prediction handling |
| `baseline_bm25.json` | Measured retrieval baseline; no routing or answer evaluation |
| `baseline_bm25_predictions.jsonl` | Raw ranked outputs behind that baseline |

| Category | Cases | Scope |
| --- | ---: | --- |
| Role descriptions | 26 | Every role in the local catalogue |
| Learning paths | 26 | Every role, with prerequisites and a practice project |
| Soft skills | 21 | Every section of the local soft-skill document |
| Work style | 7 | Interpretation and all six preference dimensions |
| Conversation | 20 | Eight core routes, intake, clarification, small talk, refusals |

Conversation cases also cover evidence provenance, insufficient evidence, missing salary
and cache data, numbers that denote years rather than skill levels, profile edits requiring
confirmation, prompt injection, personality diagnosis, off-topic questions, and other-user
privacy. Some routes have only one example; do not infer per-route reliability from this set.
Authentication, quotas, CV extraction, persistence, account deletion, UI accessibility,
numerical scoring correctness, load, and live market freshness need separate tests.

## Case format

- `id`: stable `CMG-001` through `CMG-100`.
- `query`: Thai user input, sometimes containing English technical terms.
- `category`, `difficulty`: editorial grouping and estimated difficulty, not calibrated labels.
- `context`: scenario fixture specification. Empty for standalone retrieval queries.
- `expected`: acceptable retrieved chunk IDs. Any one is sufficient for a hit; alternatives
  are not jointly required evidence. Empty on conversation cases.
- `expected_route`: exact router label for conversation cases; null on retrieval cases.
- `reference_answer_th`: supported answer example, not an exact-string target.
- `source_refs`: repository-relative sources, frozen by the manifest.
- `criteria`: case-specific human review checks, addressed by `C1`, `C2`, etc.
- `review_status`: all cases initially `pending_human_review`.

Reference answers are grounded in the repository snapshot, including local sources that
are themselves marked draft. External links in those sources have not been independently
reverified for this benchmark. Salary expectations describe the frozen reference table,
not a claim about current compensation. Scenario people and evidence IDs are synthetic.

## Run from the repository root (PowerShell)

Validate source hashes, case count, IDs, chunk labels, and the retrieval export:

```powershell
python benchmarks/careermirror_v1/benchmark.py
python -m unittest discover -s benchmarks/careermirror_v1 -p test_benchmark.py
```

Run production BM25 retrieval without downloads, external requests, or credentials:

```powershell
api/.venv/Scripts/python.exe benchmarks/careermirror_v1/benchmark.py --retrieve bm25 --output benchmarks/careermirror_v1/local_report.json --save-predictions benchmarks/careermirror_v1/local_predictions.jsonl
```

Run hybrid or vector retrieval using API dependencies. These commands load the real
embedding model and may download it on first use. They do not call the chat provider:

```powershell
api/.venv/Scripts/python.exe benchmarks/careermirror_v1/benchmark.py --retrieve hybrid --model intfloat/multilingual-e5-base --output benchmarks/careermirror_v1/local_hybrid_report.json
```

Search is deliberately unfiltered across the full corpus: the target category and role
are never supplied to retrieval. BM25 uses the production tokenizer, snapshot and search
implementation; unused vector slots are zero-filled. This is not a measurement of the
router's category/role filtering or the end-to-end chat path. The existing 30-case set and
its evaluator are unchanged.

## Conversation and answer evaluation

The included runner does not create accounts, send chat requests, or spend LLM tokens.
Use a separate isolated API adapter or manual test session for the 20 conversation fixtures:

1. Reset state between cases; use the specified profile presence, evidence, and cache state.
2. For `has_profile: false`, do not silently generate a profile. For profile fixtures,
   preserve the exact skill levels and evidence text. `context` is a semantic specification,
   not a request body or database schema; map it to the actual API's setup flow.
3. Submit only `query` and necessary fixture evidence. Never send gold labels, reference
   answers, or rubrics to the system under evaluation. Conversation history is empty unless
   explicitly supplied. A missing cache means no cached record, not zero job openings.
4. Record the returned route, answer, citations, and relevant state/tool traces. For edits,
   inspect that the state is unchanged before confirmation. For privacy and market cases,
   inspect data access and fetch traces as well as the response text.
5. A reviewer judges each criterion semantically against the reference and evidence.
   Citation numbers may differ; the cited evidence must actually support the claim.
   A paraphrase is acceptable. Do not grade by keyword overlap or exact Thai wording.

Save outputs as JSONL using the following shapes. The illustrative second row is not a
precomputed grade; replace its answer, reviewer, and criterion decisions with actual results:

```json
{"id":"CMG-001","retrieved_chunk_ids":["role-ai-engineer#role_description"]}
{"id":"CMG-081","route":"skill_assessment","answer":"<actual system answer>","reviewer":"<reviewer ID>","criteria_pass":{"C1":true,"C2":false,"C3":true}}
```

For the 80 retrieval cases, you may also collect generated answers and review their rubrics.
Merge retrieval and answer fields into one row per case; duplicate IDs are rejected.
Omit `criteria_pass` until a human has graded the response. Recording a route alone does
not demonstrate correct behavior or a correct answer.

```powershell
python benchmarks/careermirror_v1/benchmark.py --predictions benchmarks/careermirror_v1/local_predictions.jsonl --output benchmarks/careermirror_v1/local_scored_report.json
```

## Metrics and baseline

- **Hit@1 / Hit@3:** fraction of the 80 queries with at least one acceptable chunk in the
  first 1 / 3 results. This is not recall of every acceptable alternative.
- **MRR@3:** mean reciprocal rank of the first acceptable chunk, zero if absent from top 3.
- **Route accuracy:** exact matches out of all 20 conversation cases, with a confusion table.
- **Answer rubric pass rate:** passed / graded criteria, reported with grading coverage.
  All 100 cases contain 297 criteria in total. With no human grades, pass rate is null.
  The passed fraction of all criteria also shows how little has been established when
  review coverage is low. Criteria are equally weighted; there is no combined system score.

Missing predictions remain in the denominator and earn zero. A task with no supplied
outputs is unmeasured: the retrieval-only baseline's route accuracy field is conservatively
zero with `status: not_evaluated` and zero coverage. It is not evidence of routing failures.
Always publish coverage beside scores. Report provider errors and timeouts separately;
never remove those cases from the reported denominator without explaining the exclusion.

The recorded BM25 run retrieved outputs for all 80 queries:

| Metric | Result |
| --- | ---: |
| Hit@1 | 65.00% (52/80) |
| Hit@3 | 88.75% (71/80) |
| MRR@3 | 0.7542 |

By category, Hit@3 was 26/26 descriptions, 19/26 learning paths, 19/21 soft skills,
and 7/7 work-style cases. Routing, generated answers, hybrid, and vector search were not
measured in this run. Runtime and package versions are saved with the baseline.

The existing project target of Hit@3 >= 0.80 is a proposed retrieval gate, not a guarantee
of answer quality. Calibrate routing, rubric, latency and cost targets with the team before
declaring release gates. Seventy-one successes in eighty synthetic queries do not establish
production reliability. Learning-path queries often name the role, and behavioral examples
overlap conceptually with existing project tests; this is not a blind independent test set.

## Review and versioning

Before a formal report, have two domain reviewers independently check query clarity,
acceptable alternatives, reference accuracy, fixture feasibility and rubric decisions.
Resolve disagreements and record reviewer IDs, decisions and dates. The supplied
`review.md` is a checklist; no human approval is implied by automated validation.

Freeze an approved version and keep its hashes, raw predictions, model identifier and
revision, prompt revision, application commit, retrieval settings, dependency versions,
temperature, timestamp, latency and token usage with each report. Use repeated runs for
stochastic answer generation. The retrieval runner records a subset of these fields;
the conversation adapter must record the rest.

Do not tune prompts, rules or retrieval against a set and then describe it as held out.
Once used to guide a fix, retain it as a regression set and author a separate sealed test
set. The baseline has already been inspected; this version is an evaluation candidate and
regression baseline. Do not adjust labels to improve these scores.

Validation deliberately stops on dataset or source drift. To revise a label or refresh
salary data, create a reviewed new version and recompute its manifest and retrieval export
together; keep the previous version and scores. A source hash confirms reproducibility,
not that the source is correct.
