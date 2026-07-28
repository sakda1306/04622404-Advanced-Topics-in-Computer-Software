# Week 1 — LLM Data Pipeline (team project)

This folder is a `git subtree` of the team repository
[Automatic28m/Advance-AI-RAG](https://github.com/Automatic28m/Advance-AI-RAG),
taken from the branch `feature-sakda`. The pipeline takes job postings from
collection through to a question answered with citations, and each stage was
built by a different member of the team.

## My part — Vector Database + Retrieval/LLM (stage 6)

- **[`Pipeline/vector_store.py`](Pipeline/vector_store.py)** — the stage as callable
  functions: `create_collection`, `upsert`, `search`, `build_prompt`, `answer`.
- **[`Pipeline/06_vector_store.py`](Pipeline/06_vector_store.py)** — end-to-end runner:
  builds the Chroma index, runs the checks, asks one question, prints the answer
  and its sources.
- **[`main.py`](main.py)** — the front door: ask the finished pipeline a question,
  interactively or with `-q`.

What it does: indexes the 518 vectors the Embedding stage produced into a local
Chroma collection at cosine distance, searches it by top-k with metadata
filters, and hands the passages it finds to `gemini-2.5-flash`, which must cite
each claim as `[source:id#chunk]` and say it does not know rather than guess.

Three things about the input shaped it:

- **Point id is `chunk_id`, not `id`.** Jobicy numbers its postings and AIDevBoard
  uses UUIDs, so the id spaces overlap. `chunk_id` is already
  `{source}:{id}:{chunk_index}` and unique across the corpus.
- **The chunk body is joined back from `metadata_*.json`.** The vector records keep
  `embedded_text` — the header the Embedding stage prepended plus the body — but
  not the body on its own, and the header does not belong inside every passage.
- **`category` is a list, and Chroma stores only str/int/float/bool.** Categories are
  flattened into a readable joined string for citations plus one boolean key per
  category, so `{"category": "llm"}` is answered by the database rather than by
  discarding results after the search.

The runner asserts the index width matches what the Embedding stage produced,
that no chunk was dropped or duplicated, that every point can still be traced
back to a posting, that filters really narrow the result, and that every
citation resolves to a passage that was actually retrieved.

## From the team — used as input

| Stage | Files | Author |
|---|---|---|
| 1 Data Collection | `Pipeline/01_data_collection.ipynb` | team |
| 2 Cleaning | `Pipeline/02_data_cleaning.py`, `cleaning.py` | team |
| 3 Chunking | `Pipeline/03_data_chunking.py`, `chunking.py` | team |
| 4 Metadata | `Pipeline/04_metadata.py` | team |
| 5 Embedding | `Pipeline/05_embedding.py`, `embedding.py` | team |
| **6 Vector Store + Retrieval/LLM** | **`Pipeline/06_vector_store.py`, `vector_store.py`, `main.py`** | **mine** |

## Running it

`Pipeline/outputs/embeddings_*.json` and `Pipeline/chroma_db/` are gitignored —
they are large and regenerated in three commands. A `GEMINI_API_KEY` in
`Pipeline/.env` is required (see `Pipeline/.env.example`).

```bash
pip install -r requirements.txt

python Pipeline/04_metadata.py
python Pipeline/05_embedding.py --tokens-per-minute 12000 --max-batch-tokens 6000 --backoff 10
python Pipeline/06_vector_store.py

python main.py -q "which senior roles work on large language models?"
python main.py -q "remote security jobs" --category Cybersecurity --top-k 8
```

The pacing flags on stage 5 are not optional on a free Gemini key: its default
of 25k tokens/minute overruns the quota part way through and the run dies on
HTTP 429. The settings above complete all 518 chunks without a retry.

## Team members

- 116730462006-1 Phanlop Boonluea
- 116730462011-1 Saran Tanyavikai
- 116730462016-0 Sakda Baokham
- 116730462032-7 Praphavit Kaorak
- 116730462033-5 Praphakorn Pitamma
- 116730462035-0 Pitchakorn Phuadkhunthod
