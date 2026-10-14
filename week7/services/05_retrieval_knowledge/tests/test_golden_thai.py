"""eval/golden_thai.jsonl: reviewed questions that point at real documents."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.kb.trivia import load_trivia_documents
from app.schemas.search import SearchFiltersIn
from scripts.build_golden_thai import HISTORICAL_TH, OUT_OF_KB_TH, SIZES
from scripts.eval_retrieval import EVAL_DIR, load_live_documents
from scripts.eval_thai import load_historical_documents

GOLDEN = Path(__file__).parents[3] / "eval" / "golden_thai.jsonl"
TRIVIA_FILE = Path(__file__).parents[1] / "data" / "football_trivia_qa.txt"


def items() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line]


def test_ids_are_unique_and_kinds_are_sized() -> None:
    golden = items()
    assert len({item["id"] for item in golden}) == len(golden)
    counts = Counter(item["kind"] for item in golden)
    assert counts["out_of_kb_th"] == len(OUT_OF_KB_TH)
    assert counts["historical_th"] == len(HISTORICAL_TH)
    for kind, size in SIZES.items():
        assert size - 2 <= counts[kind] <= size, kind


def test_expected_documents_exist() -> None:
    known = {d.doc_id for d in load_trivia_documents(str(TRIVIA_FILE))[0]}
    known |= {d.doc_id for d in load_live_documents(EVAL_DIR)}
    known |= {d.doc_id for d in load_historical_documents(EVAL_DIR)}
    for item in items():
        assert set(item["expected_doc_ids"]) <= known, item["id"]


def test_flags_match_the_kind() -> None:
    for item in items():
        assert item["answerable"] == bool(item["expected_doc_ids"]), item["id"]
        assert item["need_all"] == (item["kind"] == "multi_doc"), item["id"]
        if item["need_all"]:
            assert len(item["expected_doc_ids"]) >= 2, item["id"]
        assert item["query_th"].strip(), item["id"]


def test_every_item_has_the_routers_routing() -> None:
    for item in items():
        routed = item["routed"]
        assert set(routed) == {"query", "query_original", "filters", "route", "intent"}, item["id"]
        assert routed["query_original"] == item["query_th"], item["id"]


def test_every_routed_filter_is_a_valid_search_filter() -> None:
    for item in items():
        SearchFiltersIn(**item["routed"]["filters"]).to_filters()


def test_true_false_trivia_is_not_a_question_source() -> None:
    trivia = {d.doc_id: d.text for d in load_trivia_documents(str(TRIVIA_FILE))[0]}
    for item in items():
        for doc_id in item["expected_doc_ids"]:
            answer = trivia.get(doc_id, "A: -").rsplit("A:", 1)[-1].strip().lower()
            assert answer not in ("f", "false"), (item["id"], doc_id)
