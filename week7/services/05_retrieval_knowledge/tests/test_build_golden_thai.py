"""Drafting the Thai golden set: repeatable picks, prompts, and the router's own routing."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from app.kb.trivia import load_trivia_documents
from scripts.build_golden_thai import (
    HISTORICAL_TH,
    OUT_OF_KB_TH,
    SIZES,
    draft_items,
    historical_items,
    parse_question,
    pick_groups,
    pick_matches,
    pick_trivia,
    question_prompt,
    routed_batch,
    routed_field,
)
from scripts.eval_retrieval import EVAL_DIR, load_live_documents

TRIVIA_FILE = Path(__file__).parents[1] / "data" / "football_trivia_qa.txt"


@pytest.fixture(scope="module")
def trivia() -> list:
    return load_trivia_documents(str(TRIVIA_FILE))[0]


@pytest.fixture(scope="module")
def live() -> list:
    return load_live_documents(EVAL_DIR)


def test_pick_trivia_is_repeatable_and_sized(trivia) -> None:
    first = pick_trivia(trivia, 40, seed=20261001)
    assert len(first) == 40
    assert [d.doc_id for d in first] == [d.doc_id for d in pick_trivia(trivia, 40, seed=20261001)]
    assert len({d.doc_id for d in first}) == 40


def test_pick_matches_covers_every_live_document(live) -> None:
    picked = pick_matches(live, 20)
    assert len(picked) == 20
    assert {d.doc_id for d, _ in picked} == {d.doc_id for d in live}
    assert all(angle in (0, 1) for _, angle in picked)


def test_pick_groups_pairs_documents(trivia, live) -> None:
    groups = pick_groups(live, trivia, 10, seed=20261001)
    assert len(groups) == 10
    assert all(len(group) == 2 for group in groups)
    live_pairs = [g for g in groups if g[0].category == "match_report"]
    assert live_pairs and all(set(a.team_ids) & set(b.team_ids) for a, b in live_pairs)


def test_question_prompt_carries_rules_and_documents(live) -> None:
    prompt = question_prompt("match_th", [live[0]], angle=1)
    assert "ภาษาไทย" in prompt and "ห้ามใส่คำตอบ" in prompt
    assert live[0].title in prompt and "22 ก.ย. 2026" in prompt
    assert "คนยิง" in prompt


def test_parse_question() -> None:
    assert parse_question('{"question": "  หงส์แดงยิงกี่ลูก "}') == "หงส์แดงยิงกี่ลูก"
    for bad in ("not json", '{"question": ""}', '{"q": "x"}'):
        with pytest.raises(ValueError):
            parse_question(bad)


def test_draft_items_shapes_every_kind(trivia, live) -> None:
    items = draft_items(trivia, live, lambda prompt: '{"question": "คำถาม"}', seed=20261001)
    counts = Counter(item["kind"] for item in items)
    assert counts == {**SIZES, "out_of_kb_th": len(OUT_OF_KB_TH)}
    assert len({item["id"] for item in items}) == len(items)
    for item in items:
        assert item["answerable"] == bool(item["expected_doc_ids"])
        assert item["need_all"] == (item["kind"] == "multi_doc")
        assert item["routed"] is None


def test_out_of_kb_covers_chatter_and_vague_questions() -> None:
    kinds = Counter(kind for _, kind in OUT_OF_KB_TH)
    assert set(kinds) == {"football", "other", "meta", "vague"}
    assert kinds["meta"] >= 5 and kinds["vague"] >= 5
    questions = {question for question, _ in OUT_OF_KB_TH}
    assert {"คุณช่วยอะไรฉันได้มั้ย", "นี้ๆ", "ใครวิ่งเร็วสุด", "ถามอะไรได้บ้าง"} <= questions


def test_routed_batch_runs_the_router_rules() -> None:
    standings, betting = routed_batch(["อาร์เซนอลอยู่อันดับเท่าไหร่", "ราคาบอลคืนนี้เป็นยังไง"])
    assert standings["route"] == "football_rag" and standings["intent"] == "standings_stats"
    assert standings["filters"]["team_ids"] == [57]
    assert betting["route"] == "decline"


def test_routed_field() -> None:
    assert routed_field("ถาม", None) == {
        "query": "ถาม",
        "query_original": "ถาม",
        "filters": {},
        "route": None,
        "intent": None,
    }
    decision = {
        "route": "football_rag",
        "intent": "match_result",
        "filters": {"season": "2026"},
        "rewritten_query": "Arsenal latest match result ถาม",
    }
    assert routed_field("ถาม", decision)["query"] == "Arsenal latest match result ถาม"
    assert routed_field("ถาม", {**decision, "rewritten_query": None})["query"] == "ถาม"


def test_historical_items_are_hand_written_archive_questions() -> None:
    items = historical_items()
    assert len(items) == len(HISTORICAL_TH) == 32
    assert len({item["id"] for item in items}) == 32
    assert len({item["query_th"] for item in items}) == 32
    for item in items:
        assert item["kind"] == "historical_th"
        assert item["answerable"] and not item["need_all"]
        assert item["expected_doc_ids"]
        assert all(doc_id.startswith("hist-") for doc_id in item["expected_doc_ids"])
