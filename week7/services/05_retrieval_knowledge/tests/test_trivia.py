"""Trivia file: parsing, duplicates and contradictions (week5 #2)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.kb.documents import doc_id_matches
from app.kb.trivia import (
    NICKNAME_FIRST_NUMBER,
    TriviaEntry,
    dedupe,
    fold,
    load_nickname_documents,
    load_trivia_documents,
    parse_trivia,
    to_document,
)

TRIVIA_FILE = Path(__file__).parents[1] / "data" / "football_trivia_qa.txt"
NICKNAME_FILE = Path(__file__).parents[1] / "data" / "thai_nicknames_qa.txt"
ALIASES_FILE = Path(__file__).parents[1] / "data" / "team_aliases.json"

SAMPLE = """# header comment
# ======

[หมวด: World Cup]
Q: Which country won the 2010  World Cup?
A: Spain

[หมวด: World Cup]
Q: which country won the 2010 world cup
A: spain

[หมวด: Ballon d'Or]
Q: Who won the Ballon d'Or in 2008?
A: Cristiano Ronaldo

[หมวด: Ballon d'Or]
Q: Who won the Ballon d'Or in 2008?
A: Lionel Messi

[หมวด: Goalkeepers]
Q: Which goalkeeper wore a rugby helmet?
A: Petr Cech

[หมวด: Goalkeepers]
Q: Which goalkeeper wore a rugby helmet?
A: Petr Čech

[หมวด: Broken]
Q: a block without an answer line
"""


def test_parse_numbers_valid_blocks_and_cleans_spacing() -> None:
    entries = parse_trivia(SAMPLE)
    assert [e.number for e in entries] == [1, 2, 3, 4, 5, 6]
    assert entries[0] == TriviaEntry(
        1, "World Cup", "Which country won the 2010 World Cup?", "Spain"
    )


def test_parse_accepts_windows_line_endings() -> None:
    assert len(parse_trivia(SAMPLE.replace("\n", "\r\n"))) == 6


def test_fold_ignores_case_accents_punctuation_and_spacing() -> None:
    assert fold("  Petr  Čech! ") == "petr cech"


def test_dedupe_keeps_first_copy_and_drops_real_conflicts() -> None:
    report = dedupe(parse_trivia(SAMPLE))
    assert report.parsed == 6
    assert [e.number for e in report.kept] == [1, 5]
    # 2 repeats 1; 6 differs from 5 only by an accent, so it is a repeat, not a conflict.
    assert report.duplicates == [2, 6]
    assert report.conflicts == [[3, 4]]


def test_answers_in_another_word_order_are_the_same_answer() -> None:
    raw = (
        "[หมวด: Copa]\nQ: Top scorers?\nA: Zizinho and Norberto Mendez\n\n"
        "[หมวด: Copa]\nQ: Top scorers?\nA: Norberto Méndez and Zizinho\n"
    )
    report = dedupe(parse_trivia(raw))
    assert report.conflicts == []
    assert report.duplicates == [2]


def test_to_document() -> None:
    doc = to_document(TriviaEntry(42, "World Cup", "Who won?", "Spain"))
    assert doc.doc_id == "trivia-0042"
    assert doc.text == "Q: Who won?\nA: Spain"
    assert (doc.category, doc.origin, doc.topic, doc.title) == (
        "trivia",
        "kb",
        "World Cup",
        "Who won?",
    )
    assert (doc.season, doc.matchweek, doc.team_ids, doc.fetched_at) == (None, None, (), None)
    long_question = "x" * 300
    assert len(to_document(TriviaEntry(1, "t", long_question, "a")).title) == 120


def test_real_trivia_file() -> None:
    documents, report = load_trivia_documents(TRIVIA_FILE)
    assert report.parsed == 1996
    assert len(documents) == 1953
    assert len(report.duplicates) == 39
    assert report.duplicates[0] == 231
    assert report.conflicts == [[523, 1839], [1804, 1838]]
    assert documents[0].doc_id == "trivia-0001"
    assert documents[0].text.endswith("\nA: Peru")
    assert len({d.doc_id for d in documents}) == 1953


def test_nickname_documents_are_numbered_after_the_trivia_file(tmp_path: Path) -> None:
    nicknames = tmp_path / "nicknames.txt"
    nicknames.write_text(SAMPLE, encoding="utf-8")
    documents, report = load_nickname_documents(nicknames)
    assert NICKNAME_FIRST_NUMBER > 1996  # never collides with trivia-0001..trivia-1996
    assert [d.doc_id for d in documents] == [
        f"trivia-{NICKNAME_FIRST_NUMBER:04d}",
        f"trivia-{NICKNAME_FIRST_NUMBER + 4:04d}",
    ]
    assert all(d.category == "trivia" for d in documents)
    assert report.duplicates == [NICKNAME_FIRST_NUMBER + 1, NICKNAME_FIRST_NUMBER + 5]


def test_real_nickname_file_names_every_league_club_and_its_thai_nickname() -> None:
    documents, report = load_nickname_documents(NICKNAME_FILE)
    assert report.duplicates == [] and report.conflicts == []
    assert all(doc_id_matches("trivia", d.doc_id) for d in documents)
    trivia_ids = {d.doc_id for d in load_trivia_documents(TRIVIA_FILE)[0]}
    assert not trivia_ids & {d.doc_id for d in documents}
    teams = json.loads(ALIASES_FILE.read_text(encoding="utf-8-sig"))["teams"]
    for team in teams:
        club = re.sub(r"\s+(?:A?FC)$|^AFC\s+", "", team["name"])
        thai = [alias for alias in team["aliases"] if re.search(r"[ก-๙]", alias)]
        matching = [d for d in documents if club in d.text]
        assert matching, club
        assert any(alias in d.text for d in matching for alias in thai), club
