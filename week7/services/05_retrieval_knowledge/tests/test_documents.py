"""doc_id rules (CONTRACT §6) and chunking (week5 #3: never by character count)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.kb.chunking import chunk_document
from app.kb.documents import Document, doc_id_matches

TITLE = "Arsenal 2–1 Chelsea · PL 2026/27 นัดที่ 5"


def match_doc(text: str) -> Document:
    return Document(
        doc_id="match-2026-mw05-57-61",
        title=TITLE,
        category="match_report",
        origin="api-football",
        text=text,
        season="2026",
        matchweek=5,
        team_ids=(57, 61),
        date="2026-09-20",
    )


@pytest.mark.parametrize(
    ("category", "doc_id", "ok"),
    [
        ("trivia", "trivia-0042", True),
        ("trivia", "trivia-42", False),
        ("match_report", "match-2026-mw05-57-61", True),
        ("match_report", "match-2026-mw5-57-61", False),
        ("standings", "standings-2026-mw05", True),
        ("standings", "standings-2026", True),
        ("standings", "standings-2026-extra", False),
        ("fixtures", "fixtures-2026-team-64", True),
        ("weekly_report", "weekly-2026-mw05", True),
        ("weekly_report", "weekly-2026-mw05-extra", False),
        ("player", "players-2026-team-57", True),
        ("player", "players-2026-team-57-extra", False),
        ("player", "coach-2026-team-66", True),
        ("player", "coach-2026-team-66-extra", False),
        ("fixtures", "coach-2026-team-66", False),
        ("player", "players-2026", False),
        ("player", "player-2026-team-57", False),
        ("fixtures", "players-2026-team-57", False),
        ("player", "fixtures-2026-team-64", False),
        ("trivia", "match-2026-mw05-57-61", False),
        ("historical", "hist-season-2004", True),
        ("historical", "hist-club-manchester-united", True),
        ("historical", "hist-club-arsenal", True),
        ("historical", "hist-records", True),
        ("historical", "hist-club-", False),
        ("historical", "hist-club-Man-Utd", False),
        ("historical", "hist-records-2025", False),
        ("historical", "hist-club-arsenal-", False),
        ("unknown", "trivia-0001", False),
    ],
)
def test_doc_id_rules(category: str, doc_id: str, ok: bool) -> None:
    assert doc_id_matches(category, doc_id) is ok


def test_trivia_is_one_chunk_with_the_question_weighted() -> None:
    doc = Document(
        doc_id="trivia-0001",
        title="Which country won the 2010 FIFA World Cup?",
        category="trivia",
        origin="kb",
        text="Q: Which country won the 2010 FIFA World Cup?\nA: Spain",
    )
    [chunk] = chunk_document(doc)
    assert chunk.chunk_id == "trivia-0001#c0"
    assert chunk.ord == 0
    assert chunk.text == doc.text
    assert chunk.bm25_text == (
        "Which country won the 2010 FIFA World Cup? "
        "Which country won the 2010 FIFA World Cup? Spain"
    )


def test_sections_split_at_level_two_headings_only() -> None:
    chunks = chunk_document(
        match_doc(
            "Arsenal 2-1 Chelsea at Emirates Stadium.\n## Goals\nSaka 12'\n### Detail\nnote\n"
            "## Cards\nNone"
        )
    )
    assert [c.chunk_id for c in chunks] == [
        "match-2026-mw05-57-61#c0",
        "match-2026-mw05-57-61#c1",
        "match-2026-mw05-57-61#c2",
    ]
    assert chunks[0].text == f"{TITLE}\nArsenal 2-1 Chelsea at Emirates Stadium."
    assert chunks[1].text == f"{TITLE}\n## Goals\nSaka 12'\n### Detail\nnote"
    assert chunks[2].text == f"{TITLE}\n## Cards\nNone"
    assert all(c.bm25_text == c.text for c in chunks)


def test_empty_preamble_is_skipped_and_ords_stay_contiguous() -> None:
    chunks = chunk_document(match_doc("## Goals\nSaka 12'\n\n## Cards\nNone"))
    assert [c.ord for c in chunks] == [0, 1]
    assert chunks[0].text == f"{TITLE}\n## Goals\nSaka 12'"


def test_text_without_headings_is_one_chunk() -> None:
    [chunk] = chunk_document(match_doc("Arsenal 2-1 Chelsea."))
    assert chunk.text == f"{TITLE}\nArsenal 2-1 Chelsea."


def test_heading_needs_a_space_after_the_hashes() -> None:
    assert len(chunk_document(match_doc("Intro\n##Goals\nSaka 12'"))) == 1


def test_content_hash_follows_every_field() -> None:
    doc = match_doc("x")
    assert doc.content_hash() == match_doc("x").content_hash()
    assert doc.content_hash() != match_doc("y").content_hash()
    assert doc.content_hash() != replace(doc, matchweek=6).content_hash()
    assert doc.content_hash() != replace(doc, team_ids=(57,)).content_hash()
