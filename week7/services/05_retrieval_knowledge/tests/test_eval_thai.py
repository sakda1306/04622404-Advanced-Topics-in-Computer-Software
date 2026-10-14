"""Thai eval logic: raw vs routed questions, router retry, multi-document hits, miss labels."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.kb.documents import Document
from app.schemas.search import SearchFiltersIn
from scripts.eval_thai import (
    ThaiOutcome,
    ThaiQuery,
    excluded_by_filters,
    label_counts,
    label_miss,
    load_thai_queries,
    misses,
    rank_for,
    returned_anyway,
    run_queries,
    summarize_thai,
)

LINES = [
    {
        "id": "th-match-001",
        "kind": "match_th",
        "query_th": "เมื่อวานหงส์แดงยิงกี่ลูก",
        "expected_doc_ids": ["match-2026-mw05-73-64"],
        "need_all": False,
        "answerable": True,
        "routed": {
            "query": "Liverpool latest match result เมื่อวานหงส์แดงยิงกี่ลูก",
            "query_original": "เมื่อวานหงส์แดงยิงกี่ลูก",
            "filters": {
                "category": ["match_report"],
                "team_ids": [64],
                "season": "2026",
                "date_from": "2026-09-21",
                "date_to": "2026-09-21",
            },
            "route": "football_rag",
            "intent": "match_result",
        },
        "note": "",
    },
    {
        "id": "th-out-001",
        "kind": "out_of_kb_th",
        "query_th": "ราคาบอลคืนนี้เป็นยังไง",
        "expected_doc_ids": [],
        "need_all": False,
        "answerable": False,
        "routed": {
            "query": "ราคาบอลคืนนี้เป็นยังไง",
            "query_original": "ราคาบอลคืนนี้เป็นยังไง",
            "filters": {},
            "route": "decline",
            "intent": "out_of_scope",
        },
        "note": "other",
    },
    {
        "id": "th-trivia-001",
        "kind": "trivia_th",
        "query_th": "ใครยิงเยอะสุดในบอลโลกปี 2002",
        "expected_doc_ids": ["trivia-0001"],
        "need_all": False,
        "answerable": True,
        "routed": {
            "query": "ใครยิงเยอะสุดในบอลโลกปี 2002",
            "query_original": "ใครยิงเยอะสุดในบอลโลกปี 2002",
            "filters": {},
            "route": None,
            "intent": None,
        },
        "note": "",
    },
]


def write_golden(tmp_path: Path) -> Path:
    path = tmp_path / "golden_thai.jsonl"
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in LINES), encoding="utf-8"
    )
    return path


class FakeSearcher:
    """Returns the scripted doc_ids per call; records the filters it was given."""

    def __init__(self, *answers: list[str]) -> None:
        self.answers = list(answers)
        self.calls: list[object] = []

    def search(self, snapshot, *, query, query_original, top_k, filters, mode):
        self.calls.append(filters)
        doc_ids = self.answers.pop(0) if self.answers else []
        snapshot.records = [SimpleNamespace(chunk=SimpleNamespace(doc_id=d)) for d in doc_ids]
        return [SimpleNamespace(position=i, rerank_score=None) for i in range(len(doc_ids))]


def query(**overrides) -> ThaiQuery:
    base = dict(
        id="q",
        kind="match_th",
        variant="routed",
        query="q",
        query_original="q",
        filters={},
        expected=frozenset({"a"}),
    )
    return ThaiQuery(**{**base, **overrides})


def outcome(q: ThaiQuery, rank: int | None, found: int = 0) -> ThaiOutcome:
    return ThaiOutcome(q, "hybrid", rank, 1 if rank else 0, found, ())


def test_load_gives_raw_and_routed_per_question(tmp_path: Path) -> None:
    queries = load_thai_queries(write_golden(tmp_path))
    assert [(q.id, q.variant) for q in queries] == [
        ("th-match-001", "raw"),
        ("th-match-001", "routed"),
        ("th-out-001", "raw"),
        ("th-out-001", "routed"),
        ("th-trivia-001", "raw"),
        ("th-trivia-001", "routed"),
    ]
    raw, routed = queries[0], queries[1]
    assert raw.query == "เมื่อวานหงส์แดงยิงกี่ลูก" and raw.filters == {}
    assert routed.query.startswith("Liverpool latest match result")
    assert routed.filters["team_ids"] == [64]
    assert queries[3].routed_away == "decline"
    assert queries[2].group == "other" and queries[3].group == "other"
    assert queries[0].group == ""
    assert queries[5].undecided and queries[5].routed_away is None


def test_routed_filters_are_valid_search_filters(tmp_path: Path) -> None:
    for q in load_thai_queries(write_golden(tmp_path)):
        SearchFiltersIn(**q.filters).to_filters()


def test_rank_for_need_all() -> None:
    assert rank_for(["x", "a", "a", "b"], frozenset({"a", "b"}), need_all=True) == 3
    assert rank_for(["x", "a"], frozenset({"a", "b"}), need_all=True) is None
    assert rank_for(["x", "a", "b"], frozenset({"a", "b"}), need_all=False) == 2


def test_routed_away_is_not_searched() -> None:
    searcher = FakeSearcher(["a"])
    [result] = run_queries(searcher, SimpleNamespace(), [query(routed_away="decline")], ("hybrid",))
    assert searcher.calls == []
    assert result.rank is None and result.returned == 0


def test_routed_retry_drops_date_and_matchweek() -> None:
    searcher = FakeSearcher([], ["a"])
    q = query(filters={"team_ids": [64], "matchweek": 5, "date_from": "2026-09-21"})
    [result] = run_queries(searcher, SimpleNamespace(), [q], ("hybrid",))
    assert len(searcher.calls) == 2
    assert searcher.calls[1].matchweek is None and searcher.calls[1].date_from is None
    assert searcher.calls[1].team_ids == (64,)
    assert result.rank == 1 and result.found == 1


def test_raw_is_not_retried() -> None:
    searcher = FakeSearcher([], ["a"])
    q = query(variant="raw", filters={"matchweek": 5})
    [result] = run_queries(searcher, SimpleNamespace(), [q], ("hybrid",))
    assert len(searcher.calls) == 1 and result.rank is None


def test_summarize_counts_router_misses_and_skips_unanswerable() -> None:
    answered = query(id="a1")
    away = query(id="a2", routed_away="clarify")
    unanswerable = query(id="u1", kind="out_of_kb_th", expected=frozenset())
    rows = summarize_thai([outcome(answered, 1), outcome(away, None), outcome(unanswerable, None)])
    assert rows == [
        {
            "kind": "match_th",
            "variant": "routed",
            "mode": "hybrid",
            "n": 2,
            "hit@1": 0.5,
            "hit@5": 0.5,
            "mrr": 0.5,
            "router_miss": 1,
            "rules_undecided": 0,
        }
    ]


def test_returned_anyway_only_reads_unanswerable() -> None:
    meta = query(id="u1", kind="out_of_kb_th", expected=frozenset(), group="meta")
    vague = query(id="u2", kind="out_of_kb_th", expected=frozenset(), group="vague")
    rows = returned_anyway([outcome(meta, None), outcome(vague, 3), outcome(query(), 1)])
    assert rows == [
        {"group": "meta", "variant": "routed", "mode": "hybrid", "n": 1, "returned_chunks": 0.0},
        {"group": "vague", "variant": "routed", "mode": "hybrid", "n": 1, "returned_chunks": 1.0},
    ]


def test_label_miss_cases() -> None:
    routed, raw, filtered = query(), query(variant="raw"), query(variant="raw_filtered")
    assert label_miss(routed=outcome(routed, 1), raw=outcome(raw, None), raw_filtered=None) is None
    away = query(routed_away="clarify")
    assert label_miss(routed=outcome(away, None), raw=outcome(raw, 1), raw_filtered=None) == (
        "router_route"
    )
    multi = query(need_all=True, expected=frozenset({"a", "b"}))
    assert (
        label_miss(routed=outcome(multi, None, found=1), raw=outcome(raw, None), raw_filtered=None)
        == "multi_doc_partial"
    )
    assert (
        label_miss(
            routed=outcome(routed, None), raw=outcome(raw, 1), raw_filtered=outcome(filtered, 2)
        )
        == "rewrite"
    )
    assert (
        label_miss(
            routed=outcome(routed, None), raw=outcome(raw, 1), raw_filtered=outcome(filtered, None)
        )
        == "router_filter"
    )
    assert (
        label_miss(
            routed=outcome(routed, 9), raw=outcome(raw, None), raw_filtered=outcome(filtered, None)
        )
        == "vocabulary"
    )


def snapshot_with(*documents: Document) -> SimpleNamespace:
    return SimpleNamespace(
        records=[
            SimpleNamespace(chunk=SimpleNamespace(doc_id=d.doc_id), document=d) for d in documents
        ]
    )


TRIVIA_DOC = Document(doc_id="a", title="t", category="trivia", origin="o", text="x")


def test_invalid_filters_are_a_router_failure_not_a_crash() -> None:
    searcher = FakeSearcher(["a"])
    [result] = run_queries(
        searcher, SimpleNamespace(), [query(filters={"team_ids": []})], ("hybrid",)
    )
    assert searcher.calls == []
    assert result.rank is None and result.query.routed_away == "invalid_filters"


def test_excluded_by_filters() -> None:
    snapshot = snapshot_with(TRIVIA_DOC)
    assert excluded_by_filters(snapshot, query(filters={"category": ["standings"], "matchweek": 5}))
    assert not excluded_by_filters(snapshot, query(filters={"category": ["trivia"]}))
    assert not excluded_by_filters(snapshot, query(filters={}))


def test_label_filtered_out_before_partial_or_vocabulary() -> None:
    raw = query(variant="raw")
    multi = query(need_all=True, expected=frozenset({"a", "b"}))
    assert (
        label_miss(
            routed=outcome(multi, None, found=1),
            raw=outcome(raw, None),
            raw_filtered=None,
            filtered_out=True,
        )
        == "router_filter"
    )
    assert (
        label_miss(
            routed=outcome(query(), None),
            raw=outcome(raw, None),
            raw_filtered=None,
            filtered_out=True,
        )
        == "router_filter"
    )


def test_miss_rows_mark_undecided_and_counts_split() -> None:
    routed = query(id="t1", undecided=True)
    raw = query(id="t1", variant="raw")
    rows = misses(
        FakeSearcher([]), snapshot_with(TRIVIA_DOC), [outcome(routed, None), outcome(raw, None)]
    )
    assert rows[0]["undecided"] is True and rows[0]["label"] == "vocabulary"
    assert label_counts(rows) == {"decided": {}, "undecided": {"vocabulary": 1}}
