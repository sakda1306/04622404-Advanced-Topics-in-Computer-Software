# Week 5 — RAG System Problems & Fixes (My Own System)

This folder follows the same structure and idea as the instructor's
[`DL-05-RAG System Development II`](https://github.com/aproot-en/Advanced-Topic-in-Computer-Software-Course/tree/main/DL-05-RAG%20System%20Development%20II),
which demonstrates common problems in LLM/RAG systems. The difference is that
every simulation here uses **my own real dataset and my own real RAG
system** — the football trivia knowledge base and pipeline built in
[`week4/DL-04-RAG System Development I/RAG-Project`](../../week4/DL-04-RAG%20System%20Development%20I/RAG-Project) —
instead of the instructor's Thai sexual-health sample data. This lets each
problem be tested against a system I actually built and actually debugged,
not an isolated sample.

Problems are added **one at a time**. Each `problemXX_*.py` first reproduces
the failure mode on real data using a small, standalone simulation (same
style as the instructor's), then explains exactly where and how the same
problem is already handled in my real week4 source code.

## Structure

```text
DL-05-RAG System Development II/
├── football_trivia_qa.txt          # Raw data / RAG Knowledge Base (copied from week4)
├── data_loader.py                  # Shared parser: football_trivia_qa.txt -> list of dict
├── main.py                         # Main menu for running each problem
├── problem01_hallucination.py      # Hallucination / answer without supporting context
└── README.md
```

## Dataset

One shared Knowledge Base of football trivia questions and answers (English),
copied from
`week4/DL-04-RAG System Development I/RAG-Project/data/football_trivia_qa.txt`.

The dataset contains **1,996 Q&A entries** across **14 categories**: General
Football Trivia, World Cup, UEFA Champions League, Player Nationality &
Background, English Premier League, UEFA European Championship, Copa
America, Ballon d'Or, Serie A, MLS, La Liga, Bundesliga, Copa Libertadores,
and Ligue 1.

Each entry has three lines:

```text
[หมวด: <category>]
Q: <question>
A: <answer>
```

Unlike the instructor's dataset, this one has no formal/casual/slang
language variants — every entry is a single, plainly worded trivia question
(the `[หมวด: ...]` header format itself is kept the same as the
instructor's template so `data_loader.py` can reuse the same parsing logic).

## Progress

| # | Problem | Main Idea | Status |
|---|---------|-----------|--------|
| 1 | Hallucination | The LLM answers without supporting context. | Done |
| 2 | Vocabulary Mismatch / Position | BoW cannot handle different wording or word order well. | Planned |
| 3 | Data Quality | Duplicate and noisy data reduce data quality. | Planned |
| 4 | Chunking | Poor chunk size or overlap can lose context. | Planned |
| 5 | Metadata Filtering | Similar content may have the wrong metadata. | Planned |
| 6 | Re-ranking | First-stage retrieval may rank the best document too low. | Planned |
| 7 | Faithfulness | Retrieval is correct, but generation changes important information. | Planned |
| 8 | RAG Configuration | Configuration controls which RAG components are active. | Planned |
| 9 | Evaluation | Measure chunking and retrieval with numerical metrics. | Planned |

Each problem is built and pushed one at a time, following the instructor's
9-problem structure, but grounded in my own week4 RAG system and the fixes
I actually applied there.

## Problem 1 — Hallucination

`problem01_hallucination.py` simulates a naive generator that fabricates a
plausible-sounding but completely false football fact when no supporting
context is retrieved (e.g. for a question totally outside the knowledge
base, such as a question about water's boiling point). It then shows the
grounded alternative that correctly refuses to answer.

The real fix already exists in my week4 system:

- `src/generator.py` → `Generator.generate()` returns
  `config.NO_CONTEXT_MESSAGE` immediately when no chunks are retrieved — the
  LLM is never even called, so it cannot hallucinate.
- `src/prompt_templates.py` → `SYSTEM_PROMPT` rule 2 explicitly instructs the
  LLM to reply with the no-context message rather than guess, even when some
  (insufficient) context is retrieved.

Run it with:

```bash
python main.py 1
```
