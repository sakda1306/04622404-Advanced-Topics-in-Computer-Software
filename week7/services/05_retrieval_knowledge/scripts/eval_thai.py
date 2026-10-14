"""Thai retrieval eval (work B, phase 1): Thai questions as typed vs as the router sends them.

    python -m scripts.eval_thai

Reads eval/golden_thai.jsonl (scripts/build_golden_thai.py). Every question runs twice:
- raw:    the Thai question as typed, no filters
- routed: the router's rewrite and filters stored in the file, with the router's retry that
          drops matchweek/date filters when nothing comes back (03 Router.route)
A routed question the router declines or answers with clarify is a router miss and is not
searched. Each routed miss gets a cause label so phase 2 can pick a fix. Results go to
eval/results/retrieval_thai.json; scripts/eval_retrieval.py and its report are unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.clock import bangkok_now, version_stamp
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.kb.documents import Document
from app.kb.store import KnowledgeStore
from app.kb.trivia import load_trivia_documents
from app.schemas.search import SearchFiltersIn
from app.search.aliases import load_alias_file
from app.search.embedder import SentenceTransformerEmbedder
from app.search.hybrid import Mode, Searcher
from app.search.snapshot import Snapshot
from scripts.eval_retrieval import (
    EVAL_DIR,
    MODES,
    _jsonl,
    _search,
    copy_knowledge_base,
    load_live_documents,
    prepare_index,
    provenance,
)

GOLDEN_FILE = EVAL_DIR / "golden_thai.jsonl"
HISTORICAL_FIXTURE = "historical_docs.json.gz"
TOP = 5  # generation reads the first five chunks
RETRY_DROPS = ("matchweek", "date_from", "date_to")


@dataclass(frozen=True, slots=True)
class ThaiQuery:
    id: str
    kind: str  # trivia_th | match_th | multi_doc | out_of_kb_th | historical_th
    variant: str  # raw | routed | raw_filtered
    query: str
    query_original: str | None
    filters: dict[str, Any] = field(hash=False)
    expected: frozenset[str] = frozenset()
    need_all: bool = False  # multi_doc: a hit needs every expected document
    routed_away: str | None = None  # the route when the router does not search
    undecided: bool = False  # the rules could not decide; the classifier/LLM would
    group: str = ""  # out_of_kb_th only: football | other | meta | vague


@dataclass(frozen=True, slots=True)
class ThaiOutcome:
    query: ThaiQuery
    mode: str
    rank: int | None  # rank at which the question counts as answered; None = not in DEPTH
    returned: int  # documents returned
    found: int  # expected documents in the first TOP
    top: tuple[str, ...]  # first TOP documents


def load_historical_documents(eval_dir: Path) -> list[Document]:
    """07's Premier League archive (CONTRACT v1.11), exported once and stored compressed."""
    raw = gzip.decompress((eval_dir / "fixtures" / HISTORICAL_FIXTURE).read_bytes())
    return [
        Document(**{**d, "team_ids": tuple(d["team_ids"])})
        for d in json.loads(raw.decode("utf-8"))["documents"]
    ]


def load_thai_queries(path: Path = GOLDEN_FILE) -> list[ThaiQuery]:
    queries: list[ThaiQuery] = []
    for item in _jsonl(path):
        common = {
            "id": item["id"],
            "kind": item["kind"],
            "expected": frozenset(item["expected_doc_ids"]),
            "need_all": bool(item.get("need_all")),
            "group": item.get("note", "") if item["kind"] == "out_of_kb_th" else "",
        }
        text = item["query_th"]
        queries.append(
            ThaiQuery(variant="raw", query=text, query_original=text, filters={}, **common)
        )
        routed = item["routed"]
        route = routed.get("route")
        queries.append(
            ThaiQuery(
                variant="routed",
                query=routed["query"],
                query_original=routed["query_original"],
                filters=dict(routed.get("filters") or {}),
                routed_away=route if route not in (None, "football_rag") else None,
                undecided=route is None,
                **common,
            )
        )
    return queries


def rank_for(doc_ids: Sequence[str], expected: frozenset[str], *, need_all: bool) -> int | None:
    seen: list[str] = []
    found: set[str] = set()
    for doc_id in doc_ids:
        if doc_id in seen:
            continue
        seen.append(doc_id)
        if doc_id in expected:
            found.add(doc_id)
            if not need_all or found == expected:
                return len(seen)
    return None


def _without_retry_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in filters.items() if key not in RETRY_DROPS}


def _valid_filters(filters: dict[str, Any]) -> bool:
    try:
        SearchFiltersIn(**filters)
    except ValidationError:
        return False
    return True


def excluded_by_filters(snapshot: Snapshot, query: ThaiQuery) -> bool:
    """An expected document the query's filters can never return (no search needed)."""
    if not query.filters or not _valid_filters(query.filters):
        return False
    filters = SearchFiltersIn(**query.filters).to_filters()
    documents = {r.chunk.doc_id: r.document for r in snapshot.records}
    return any(
        doc_id in documents and not filters.accepts(documents[doc_id]) for doc_id in query.expected
    )


def run_queries(
    searcher: Searcher, snapshot: Snapshot, queries: Iterable[ThaiQuery], modes: Sequence[Mode]
) -> list[ThaiOutcome]:
    outcomes: list[ThaiOutcome] = []
    for query in queries:
        if not query.routed_away and not _valid_filters(query.filters):
            # 05 answers such a request with 422; the router would report retrieval as down.
            query = replace(query, routed_away="invalid_filters")
        for mode in modes:
            if query.routed_away:
                outcomes.append(ThaiOutcome(query, mode, None, 0, 0, ()))
                continue
            doc_ids, _, _ = _search(searcher, snapshot, query, mode)
            if not doc_ids and query.variant == "routed" and set(query.filters) & set(RETRY_DROPS):
                retry = replace(query, filters=_without_retry_filters(query.filters))
                doc_ids, _, _ = _search(searcher, snapshot, retry, mode)
            unique = tuple(dict.fromkeys(doc_ids))
            top = unique[:TOP]
            rank = rank_for(doc_ids, query.expected, need_all=query.need_all)
            outcomes.append(
                ThaiOutcome(query, mode, rank, len(unique), len(set(top) & query.expected), top)
            )
    return outcomes


def _hit(outcome: ThaiOutcome, k: int) -> bool:
    return outcome.rank is not None and outcome.rank <= k


def summarize_thai(outcomes: Sequence[ThaiOutcome]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[ThaiOutcome]] = {}
    for outcome in outcomes:
        if outcome.query.expected:
            key = (outcome.query.kind, outcome.query.variant, outcome.mode)
            groups.setdefault(key, []).append(outcome)
    rows = []
    for (kind, variant, mode), group in sorted(groups.items()):
        n = len(group)
        rows.append(
            {
                "kind": kind,
                "variant": variant,
                "mode": mode,
                "n": n,
                "hit@1": sum(_hit(o, 1) for o in group) / n,
                "hit@5": sum(_hit(o, TOP) for o in group) / n,
                "mrr": sum(1 / o.rank for o in group if o.rank) / n,
                "router_miss": sum(o.query.routed_away is not None for o in group),
                "rules_undecided": sum(o.query.undecided for o in group),
            }
        )
    return rows


def returned_anyway(outcomes: Sequence[ThaiOutcome]) -> list[dict[str, Any]]:
    """Unanswerable questions that still got documents back, per kind of question."""
    groups: dict[tuple[str, str, str], list[ThaiOutcome]] = {}
    for outcome in outcomes:
        if not outcome.query.expected:
            key = (outcome.query.group, outcome.query.variant, outcome.mode)
            groups.setdefault(key, []).append(outcome)
    return [
        {
            "group": name,
            "variant": variant,
            "mode": mode,
            "n": len(group),
            "returned_chunks": sum(o.returned > 0 for o in group) / len(group),
        }
        for (name, variant, mode), group in sorted(groups.items())
    ]


def label_miss(
    *,
    routed: ThaiOutcome,
    raw: ThaiOutcome,
    raw_filtered: ThaiOutcome | None,
    filtered_out: bool = False,
) -> str | None:
    """Why the routed question missed its documents in the first TOP (spec §5)."""
    if _hit(routed, TOP):
        return None
    if routed.query.routed_away:
        return "router_route"
    if filtered_out:  # no rewording can bring back a document the filters exclude
        return "router_filter"
    if routed.query.need_all and routed.found > 0:
        return "multi_doc_partial"
    if raw_filtered is not None and _hit(raw_filtered, TOP):
        return "rewrite"
    if _hit(raw, TOP):
        return "router_filter"
    return "vocabulary"


def misses(
    searcher: Searcher, snapshot: Snapshot, outcomes: Sequence[ThaiOutcome]
) -> list[dict[str, Any]]:
    hybrid = {(o.query.id, o.query.variant): o for o in outcomes if o.mode == "hybrid"}
    rows = []
    for (qid, variant), routed in sorted(hybrid.items()):
        if variant != "routed" or not routed.query.expected or _hit(routed, TOP):
            continue
        raw = hybrid[(qid, "raw")]
        raw_filtered = None
        if not routed.query.routed_away:
            probe = replace(raw.query, variant="raw_filtered", filters=routed.query.filters)
            [raw_filtered] = run_queries(searcher, snapshot, [probe], ("hybrid",))
        filtered_out = excluded_by_filters(snapshot, routed.query)
        label = label_miss(
            routed=routed, raw=raw, raw_filtered=raw_filtered, filtered_out=filtered_out
        )
        rows.append(
            {
                "id": qid,
                "kind": routed.query.kind,
                "label": label,
                # The rules could not decide: "routed" stands in for the classifier/LLM path.
                "undecided": routed.query.undecided,
                "query_th": raw.query.query,
                "routed_query": routed.query.query,
                "filters": routed.query.filters,
                "routed_away": routed.query.routed_away,
                "expected": sorted(routed.query.expected),
                "top5": list(routed.top),
            }
        )
    return rows


def label_counts(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Miss labels, split by whether the router's rules decided the question."""
    counts: dict[str, Counter[str]] = {"decided": Counter(), "undecided": Counter()}
    for row in rows:
        counts["undecided" if row["undecided"] else "decided"][row["label"]] += 1
    return {name: dict(sorted(counter.items())) for name, counter in counts.items()}


def table(rows: Sequence[dict[str, Any]]) -> str:
    header = ("kind", "variant", "mode", "n", "hit@1", "hit@5", "mrr", "away")
    lines = ["{:<14}{:<9}{:<8}{:>4}{:>8}{:>8}{:>7}{:>6}".format(*header)]
    for r in rows:
        lines.append(
            f"{r['kind']:<14}{r['variant']:<9}{r['mode']:<8}{r['n']:>4}"
            f"{r['hit@1']:>8.2f}{r['hit@5']:>8.2f}{r['mrr']:>7.2f}{r['router_miss']:>6}"
        )
    return "\n".join(lines)


async def _run(args: argparse.Namespace, store: KnowledgeStore) -> dict[str, Any]:
    settings = get_settings()
    embedder = SentenceTransformerEmbedder(settings.embedding_model)
    trivia, _ = load_trivia_documents(settings.trivia_file)
    documents = [
        *trivia,
        *load_live_documents(args.eval_dir),
        *load_historical_documents(args.eval_dir),
    ]
    index = await prepare_index(store, embedder, documents)
    snapshot = index.snapshot
    assert snapshot is not None
    searcher = Searcher(
        embedder,
        load_alias_file(settings.aliases_file),
        reranker=None,
        candidate_k=settings.candidate_k,
        rrf_k=settings.rrf_k,
        min_vector_score=0.0,
    )
    queries = load_thai_queries(args.eval_dir / "golden_thai.jsonl")
    run_queries(searcher, snapshot, queries[:4], MODES)  # warm-up, not reported
    outcomes = run_queries(searcher, snapshot, queries, MODES)
    miss_rows = misses(searcher, snapshot, outcomes)
    kinds = Counter(q.kind for q in queries if q.variant == "raw")
    return {
        "generated_at": version_stamp(bangkok_now()),
        "embedding_model": settings.embedding_model,
        "golden_file": "eval/golden_thai.jsonl",
        "questions": dict(sorted(kinds.items())),
        "metric_note": (
            "multi_doc hit@5 needs every expected document in the top 5; routed questions the "
            "rules cannot decide are searched as raw Thai, so their misses and returned chunks "
            "stand in for the classifier/LLM path"
        ),
        "measured_on": provenance(),
        "results": summarize_thai(outcomes),
        "unanswerable_returned_chunks": returned_anyway(outcomes),
        "miss_labels": label_counts(miss_rows),
        "misses": miss_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kb", help="knowledge base to copy (default: KB_DB_PATH)")
    parser.add_argument("--eval-dir", type=Path, default=EVAL_DIR)
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results" / "retrieval_thai.json")
    args = parser.parse_args()
    configure_logging("WARNING", False, "retrieval-eval-thai")

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
    print(table(report["results"]))
    print(f"\nmiss labels: {report['miss_labels']}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
