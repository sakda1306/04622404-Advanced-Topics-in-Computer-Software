"""The trivia golden set: exact size, the knowledge base's category mix, sound variants."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.kb.trivia import load_trivia_documents
from scripts.build_golden import (
    STOPWORDS,
    allocate,
    build_items,
    make_natural,
    make_partial,
    make_slang,
)

TRIVIA_FILE = Path(__file__).parents[1] / "data" / "football_trivia_qa.txt"
GOLDEN_FILE = Path(__file__).parents[3] / "eval" / "golden_trivia.jsonl"


@pytest.fixture(scope="module")
def documents() -> list:
    return load_trivia_documents(str(TRIVIA_FILE))[0]


def test_allocate_gives_exactly_the_size_in_proportion() -> None:
    shares = allocate(Counter({"a": 847, "b": 355, "c": 229, "d": 9}), 60)
    assert sum(shares.values()) == 60
    assert shares == {"a": 35, "b": 15, "c": 10, "d": 0}


def test_golden_set_has_60_items_in_the_knowledge_base_mix(documents: list) -> None:
    items = build_items(documents, size=60, seed=42)
    assert len(items) == 60
    assert len({i["doc_id"] for i in items}) == 60
    expected = allocate(Counter(d.topic for d in documents), 60)
    assert Counter(i["category"] for i in items) == +Counter(expected)


def test_golden_set_is_the_same_every_run(documents: list) -> None:
    assert build_items(documents, size=60, seed=42) == build_items(documents, size=60, seed=42)


def test_every_item_points_at_a_real_trivia_document(documents: list) -> None:
    by_id = {d.doc_id: d for d in documents}
    for item in build_items(documents, size=60, seed=42):
        assert item["variants"]["verbatim"] in by_id[item["doc_id"]].text


def test_partial_keeps_the_topic_not_the_question_word() -> None:
    # week5 #5: "Who" survived because it was compared before lower-casing.
    partial = make_partial("Who holds the record for most goals in the Copa Libertadores?")
    assert partial == "holds record goals copa libertadores"
    assert not set(partial.split()) & STOPWORDS


def test_slang_rewrites_formal_terms() -> None:
    assert make_slang("Who won the English Premier League in 1995?") == ("Who won the EPL in 1995?")
    assert make_slang("In which year did Pele retire?") is None


def test_natural_reads_like_a_person_typing() -> None:
    natural = make_natural("Which country won the 2010 FIFA World Cup?", seed_text="x")
    assert "?" not in natural
    assert natural.islower()
    assert "which country won the 2010 fifa world cup" in natural


def test_committed_golden_file_matches_the_builder(documents: list) -> None:
    lines = GOLDEN_FILE.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == build_items(documents, size=60, seed=42)
