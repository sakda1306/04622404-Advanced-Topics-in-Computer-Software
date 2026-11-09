# CareerMirror evaluation v2

The master file golden_th.jsonl contains 200 Thai cases. CMG-001 through CMG-100 reproduce v1. Review.md displays the questions, contexts, reference answers and criteria together.

| Added cases | Capability | Count |
|---|---|---:|
| 101–126 | Compare two related roles and justify which better fits the stated responsibilities | 26 |
| 127–152 | Continue a learning plan from a given starting point and identify a practice project | 26 |
| 153–173 | Infer a soft skill from an observed workplace behavior | 21 |
| 174–180 | Interpret work preferences in context | 7 |
| 181–188 | Resolve follow-up questions using salary sources, proxy rows or missing records | 8 |
| 189–200 | Distinguish evidence from inference, handle edits, missing information and refusals | 12 |

Run from the repository root in PowerShell.

```powershell
python benchmarks/careermirror_v1/benchmark.py --suite v2
api/.venv/Scripts/python.exe benchmarks/careermirror_v1/benchmark.py --suite v2 --retrieve bm25
python benchmarks/careermirror_v1/benchmark.py --suite v2 --predictions predictions.jsonl
```

The retrieval denominator is 134 and the conversation denominator is 66. See the [evaluation protocol](../careermirror_v1/README.md#conversation-and-answer-evaluation) for prediction fields, fixture setup and human grading. For conversation runs, submit each query with its fixture and recent messages. Keep expected routes, reference answers and criteria hidden from the system. Judge the returned explanation criterion by criterion and report grading coverage alongside pass rate. Route accuracy alone measures routing.

The included BM25 baseline found an acceptable source in the top three for 121/134 queries. Conversation and answer grading are pending. The cases are synthetic, reuse project source material and await human review. Report performance by task. For longitudinal comparisons, score identical case IDs under both system versions.
