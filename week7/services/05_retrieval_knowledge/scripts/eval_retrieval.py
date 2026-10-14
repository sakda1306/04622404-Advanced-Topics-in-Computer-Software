"""Retrieval eval (week5 #5): hit@1 / hit@5 / MRR / latency per mode, and MIN_VECTOR_SCORE.

    python -m scripts.eval_retrieval                        # bm25, vector, hybrid
    python -m scripts.eval_retrieval --rerank BAAI/bge-reranker-v2-m3

Runs in process with the real embedding model on a copy of the knowledge base, so the
service's own KB is never touched: KB_DB_PATH is copied with SQLite's backup API (writes
still in the WAL are included) if it exists, otherwise the trivia file is ingested into a
temporary store. The frozen live-data fixture is added to the copy.

Golden sets (root `eval/`):
- golden_trivia.jsonl    60 trivia questions x 4 phrasings (scripts/build_golden.py)
- golden_match.jsonl     20 questions as the router sends them: English query, Thai
                         original with nicknames, filters; over fixtures/live_docs.json
- golden_out_of_kb.jsonl questions the knowledge base cannot answer: `kind` football
                         (matches, tables, news not ingested) or other (not football)

A hit is the expected document anywhere in the first k documents (chunks of one document
count once). For unanswerable questions it reports how often chunks come back anyway, and
whether a cut-off on the top rerank_score could separate answerable from unanswerable.
The results, with the machine and library versions, go to eval/results/retrieval.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sqlite3
import tempfile
import time
from collections.abc import Iterable, Sequence
from contextlib import closing
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from app.core.clock import bangkok_now, version_stamp
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.index.service import IndexService
from app.kb.documents import Document
from app.kb.store import KnowledgeStore
from app.kb.trivia import load_trivia_documents
from app.schemas.search import SearchFiltersIn
from app.search.aliases import load_alias_file
from app.search.embedder import Embedder, SentenceTransformerEmbedder
from app.search.hybrid import Mode, Searcher
from app.search.reranker import CrossEncoderReranker
from app.search.snapshot import Snapshot

SERVICE = Path(__file__).parents[1]
EVAL_DIR = SERVICE.parents[1] / "eval"
MODES: tuple[Mode, ...] = ("bm25", "vector", "hybrid")
DEPTH = 20  # documents looked at per question; MRR counts ranks up to here
THRESHOLDS = (0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6)
# ms-marco returns logits; bge-reranker-v2-m3 returns probabilities (sigmoid).
LOGIT_THRESHOLDS = (-8.0, -6.0, -4.0, -2.0, 0.0, 2.0, 4.0)
PROBABILITY_THRESHOLDS = (0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9)


@dataclass(frozen=True, slots=True)
class Query:
    set: str  # trivia | match | out_of_kb
    variant: str  # trivia: verbatim | slang | partial | natural · out_of_kb: football | other
    id: str
    query: str
    query_original: str | None
    filters: dict[str, Any]
    expected: frozenset[str]  # empty: nothing in the knowledge base answers it


@dataclass(frozen=True, slots=True)
class Outcome:
    query: Query
    mode: str
    rank: int | None  # 1-based rank of the first expected document; None = not found
    latency_ms: float
    returned: int = 0  # documents returned
    top_rerank: float | None = None  # rerank_score of the first hit, when reranking


def _jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_queries(eval_dir: Path) -> list[Query]:
    queries = [
        Query("trivia", variant, item["id"], text, None, {}, frozenset({item["doc_id"]}))
        for item in _jsonl(eval_dir / "golden_trivia.jsonl")
        for variant, text in item["variants"].items()
    ]
    queries += [
        Query(
            "match",
            "match",
            item["id"],
            item["query"],
            item.get("query_original"),
            item.get("filters", {}),
            frozenset(item["expected_doc_ids"]),
        )
        for item in _jsonl(eval_dir / "golden_match.jsonl")
    ]
    queries += [
        Query(
            "out_of_kb",
            item.get("kind", "other"),
            item["id"],
            item["query"],
            item.get("query_original"),
            item.get("filters", {}),
            frozenset(),
        )
        for item in _jsonl(eval_dir / "golden_out_of_kb.jsonl")
    ]
    return queries


def load_live_documents(eval_dir: Path) -> list[Document]:
    data = json.loads((eval_dir / "fixtures" / "live_docs.json").read_text(encoding="utf-8"))
    return [Document(**{**d, "team_ids": tuple(d["team_ids"])}) for d in data["documents"]]


def first_rank(doc_ids: Sequence[str], expected: frozenset[str]) -> int | None:
    seen: list[str] = []
    for doc_id in doc_ids:
        if doc_id in seen:
            continue
        seen.append(doc_id)
        if doc_id in expected:
            return len(seen)
    return None


def percentile(values: Sequence[float], p: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), p))


async def prepare_index(
    store: KnowledgeStore, embedder: Embedder, extra: Sequence[Document]
) -> IndexService:
    index = IndexService(store, embedder)
    await index.load()
    await index.upsert(extra)
    return index


def _search(
    searcher: Searcher, snapshot: Snapshot, query: Query, mode: Mode
) -> tuple[list[str], float, float | None]:
    started = time.perf_counter()
    hits = searcher.search(
        snapshot,
        query=query.query,
        query_original=query.query_original,
        top_k=DEPTH,
        filters=SearchFiltersIn(**query.filters).to_filters(),
        mode=mode,
    )
    latency = (time.perf_counter() - started) * 1000
    top = hits[0].rerank_score if hits else None
    return [snapshot.records[h.position].chunk.doc_id for h in hits], latency, top


def evaluate(
    searcher: Searcher, snapshot: Snapshot, queries: Iterable[Query], *, modes: Sequence[Mode]
) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for query in queries:
        for mode in modes:
            doc_ids, latency, top = _search(searcher, snapshot, query, mode)
            rank = first_rank(doc_ids, query.expected)
            returned = len(dict.fromkeys(doc_ids))
            outcomes.append(Outcome(query, mode, rank, latency, returned, top))
    return outcomes


def summarize(outcomes: Sequence[Outcome], label: str = "") -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Outcome]] = {}
    for outcome in outcomes:
        if not outcome.query.expected:
            continue  # unanswerable questions: see answered_anyway() and abstention()
        mode = f"{outcome.mode}{label}"
        groups.setdefault((outcome.query.set, outcome.query.variant, mode), []).append(outcome)
    rows = []
    for (set_, variant, mode), group in groups.items():
        ranks = [o.rank for o in group]
        latencies = [o.latency_ms for o in group]
        rows.append(
            {
                "set": set_,
                "variant": variant,
                "mode": mode,
                "n": len(group),
                "hit@1": sum(r == 1 for r in ranks) / len(group),
                "hit@5": sum(r is not None and r <= 5 for r in ranks) / len(group),
                "mrr": sum(1 / r for r in ranks if r) / len(group),
                "p50_ms": percentile(latencies, 50),
                "p95_ms": percentile(latencies, 95),
            }
        )
    return rows


def answered_anyway(outcomes: Sequence[Outcome], label: str = "") -> list[dict[str, Any]]:
    """Unanswerable questions that still got chunks back (false positives of retrieval)."""
    groups: dict[tuple[str, str], list[Outcome]] = {}
    for outcome in outcomes:
        if not outcome.query.expected:
            key = (outcome.query.variant, f"{outcome.mode}{label}")
            groups.setdefault(key, []).append(outcome)
    return [
        {
            "kind": kind,
            "mode": mode,
            "n": len(group),
            "returned_chunks": sum(o.returned > 0 for o in group) / len(group),
        }
        for (kind, mode), group in sorted(groups.items())
    ]


def _thresholds_for(outcomes: Sequence[Outcome]) -> tuple[float, ...]:
    scores = [o.top_rerank for o in outcomes if o.top_rerank is not None]
    probabilities = bool(scores) and all(0.0 <= s <= 1.0 for s in scores)
    return PROBABILITY_THRESHOLDS if probabilities else LOGIT_THRESHOLDS


def abstention(
    outcomes: Sequence[Outcome], thresholds: Sequence[float], label: str
) -> list[dict[str, Any]]:
    """If callers refused to answer when the top rerank_score is below a cut-off.

    - answerable_refused: answerable questions that would be refused
    - answerable_kept_right: ... not refused and the expected document is first
    - unanswerable_answered_<kind>: unanswerable questions that would still be answered
    """
    answerable = [o for o in outcomes if o.query.expected]
    unanswerable: dict[str, list[Outcome]] = {}
    for o in outcomes:
        if not o.query.expected:
            unanswerable.setdefault(o.query.variant, []).append(o)

    def passes(o: Outcome, t: float) -> bool:
        return o.top_rerank is not None and o.top_rerank >= t

    rows = []
    for t in thresholds:
        row: dict[str, Any] = {
            "mode": label,
            "threshold": t,
            "answerable_refused": sum(not passes(o, t) for o in answerable)
            / max(len(answerable), 1),
            "answerable_kept_right": sum(passes(o, t) and o.rank == 1 for o in answerable)
            / max(len(answerable), 1),
        }
        for kind, group in sorted(unanswerable.items()):
            row[f"unanswerable_answered_{kind}"] = sum(passes(o, t) for o in group) / len(group)
        rows.append(row)
    return rows


def sweep_min_vector_score(
    searcher: Searcher,
    embedder: Embedder,
    snapshot: Snapshot,
    queries: Sequence[Query],
    thresholds: Sequence[float],
) -> list[dict[str, Any]]:
    """What a MIN_VECTOR_SCORE cut-off would do.

    - in_kb_lost: answerable questions whose expected document the vector side found,
      but below the cut-off (it would be dropped from the vector list)
    - out_of_kb_empty_vector: unanswerable questions with no vector hit left
    - out_of_kb_empty_hybrid: ... and no BM25 hit either, so hybrid returns `chunks: []`
    """
    in_kb: list[float | None] = []
    out_vector: list[float | None] = []  # None: the filters left nothing to search
    out_bm25_empty: list[bool] = []
    for query in queries:
        filters = SearchFiltersIn(**query.filters).to_filters()
        allowed = snapshot.allowed(filters)
        vector = embedder.encode([query.query])[0]  # what Searcher embeds
        scored = snapshot.vector_top(vector, allowed, DEPTH, 0.0)
        if query.expected:
            found = [s for p, s in scored if snapshot.records[p].chunk.doc_id in query.expected]
            in_kb.append(max(found) if found else None)
        else:
            out_vector.append(max((s for _, s in scored), default=None))
            bm25 = searcher.search(
                snapshot,
                query=query.query,
                query_original=query.query_original,
                top_k=DEPTH,
                filters=filters,
                mode="bm25",
            )
            out_bm25_empty.append(not bm25)

    found_scores = [s for s in in_kb if s is not None]
    rows = []
    for t in thresholds:
        vector_empty = [top is None or top < t for top in out_vector]
        rows.append(
            {
                "threshold": t,
                "in_kb_lost": sum(s < t for s in found_scores) / max(len(in_kb), 1),
                "out_of_kb_empty_vector": sum(vector_empty) / max(len(out_vector), 1),
                "out_of_kb_empty_hybrid": sum(
                    v and b for v, b in zip(vector_empty, out_bm25_empty, strict=True)
                )
                / max(len(out_vector), 1),
            }
        )
    return rows


def _table(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "| set | variant | mode | n | hit@1 | hit@5 | MRR | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['set']} | {r['variant']} | {r['mode']} | {r['n']} | {r['hit@1']:.3f} "
            f"| {r['hit@5']:.3f} | {r['mrr']:.3f} | {r['p50_ms']:.0f} | {r['p95_ms']:.0f} |"
        )
    return "\n".join(lines)


def _sweep_table(rows: Sequence[dict[str, Any]]) -> str:
    lines = [
        "| MIN_VECTOR_SCORE | in-KB hits dropped "
        "| out-of-KB empty (vector) | out-of-KB empty (hybrid) |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['threshold']:.2f} | {r['in_kb_lost']:.1%} | {r['out_of_kb_empty_vector']:.0%} "
            f"| {r['out_of_kb_empty_hybrid']:.0%} |"
        )
    return "\n".join(lines)


async def _run(args: argparse.Namespace, store: KnowledgeStore) -> dict[str, Any]:
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    queries = load_queries(args.eval_dir)
    trivia, _ = load_trivia_documents(settings.trivia_file)
    # Unchanged trivia is skipped, so a copied KB embeds only the live fixture.
    index = await prepare_index(store, embedder, [*trivia, *load_live_documents(args.eval_dir)])
    snapshot = index.snapshot
    assert snapshot is not None
    aliases = load_alias_file(settings.aliases_file)

    def searcher(reranker: CrossEncoderReranker | None = None) -> Searcher:
        return Searcher(
            embedder,
            aliases,
            reranker=reranker,
            candidate_k=settings.candidate_k,
            rrf_k=settings.rrf_k,
            min_vector_score=0.0,
        )

    base = searcher()
    evaluate(base, snapshot, queries[:3], modes=MODES)  # warm-up, not measured
    outcomes = evaluate(base, snapshot, queries, modes=MODES)
    rows = summarize(outcomes)
    anyway = answered_anyway(outcomes)
    refusals: list[dict[str, Any]] = []
    for model in args.rerank:
        label = f"+rerank:{model.split('/')[-1]}"
        reranked = searcher(CrossEncoderReranker(model))  # fails loudly: no silent fallback
        evaluate(reranked, snapshot, queries[:3], modes=("hybrid",))  # warm-up
        outcomes = evaluate(reranked, snapshot, queries, modes=("hybrid",))
        rows += summarize(outcomes, label=label)
        anyway += answered_anyway(outcomes, label=label)
        refusals += abstention(outcomes, _thresholds_for(outcomes), f"hybrid{label}")
    sweep = sweep_min_vector_score(base, embedder, snapshot, queries, args.thresholds)
    kb = {"chunks": snapshot.size, "documents": len({r.chunk.doc_id for r in snapshot.records})}

    counts: dict[str, int] = {}
    for query in queries:
        counts[f"{query.set}/{query.variant}"] = counts.get(f"{query.set}/{query.variant}", 0) + 1
    return {
        "generated_at": version_stamp(bangkok_now()),
        "embedding_model": settings.embedding_model,
        "depth": DEPTH,
        "candidate_k": settings.candidate_k,
        "rrf_k": settings.rrf_k,
        "knowledge_base": kb,
        "live_fixture_synthetic": True,
        "questions": counts,
        "measured_on": provenance(),
        "results": sorted(rows, key=lambda r: (r["set"], r["variant"], r["mode"])),
        "unanswerable_returned_chunks": anyway,
        "rerank_abstention": refusals,
        "min_vector_score": sweep,
    }


def provenance() -> dict[str, Any]:
    """Where and how the numbers were measured, so they are not read out of context."""
    versions = {}
    for package in ("torch", "sentence-transformers", "faiss-cpu", "rank-bm25", "numpy"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "versions": versions,
        "conditions": (
            "one process, CPU only, models loaded and warmed up before timing; latency is "
            "Searcher.search in process: no HTTP, no model loading, no other load on the machine"
        ),
    }


def copy_knowledge_base(source: Path, dest: Path) -> None:
    """A consistent copy with SQLite's backup API; a file copy misses writes in the WAL."""
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(dest)) as dst:
        src.backup(dst)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb", help="knowledge base to copy (default: KB_DB_PATH)")
    parser.add_argument("--rerank", action="append", default=[], help="cross-encoder to compare")
    parser.add_argument("--eval-dir", type=Path, default=EVAL_DIR)
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results" / "retrieval.json")
    parser.add_argument("--thresholds", type=float, nargs="+", default=list(THRESHOLDS))
    args = parser.parse_args()
    configure_logging("WARNING", False, "retrieval-eval")

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "kb.sqlite"
        source = Path(args.kb or get_settings().kb_db_path)
        if source.exists():
            copy_knowledge_base(source, db)
        store = KnowledgeStore(str(db))
        try:
            report = asyncio.run(_run(args, store))
        finally:
            store.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(_table(report["results"]))
    print()
    print(_sweep_table(report["min_vector_score"]))
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
