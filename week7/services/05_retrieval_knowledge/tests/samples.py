"""A small knowledge base used across the tests: 3 trivia + 3 live-data documents (9 chunks)."""

from __future__ import annotations

from app.kb.documents import Document
from app.kb.trivia import TriviaEntry, to_document

FETCHED_AT = "2026-09-21T09:00:00+07:00"


def trivia(number: int, question: str, answer: str, topic: str = "General") -> Document:
    return to_document(TriviaEntry(number, topic, question, answer))


MATCH = Document(
    doc_id="match-2026-mw05-57-61",
    title="Arsenal 2–1 Chelsea · PL 2026/27 นัดที่ 5",
    category="match_report",
    origin="api-football",
    text=(
        "Premier League 2026/27, matchweek 5, 20 Sep 2026 at Emirates Stadium. "
        "Arsenal 2-1 Chelsea.\n## Goals\nSaka 12', Havertz 55' for Arsenal; Palmer 70' for Chelsea."
    ),
    season="2026",
    matchweek=5,
    team_ids=(57, 61),
    date="2026-09-20",
    fetched_at=FETCHED_AT,
)
STANDINGS = Document(
    doc_id="standings-2026-mw05",
    title="Premier League table after matchweek 5",
    category="standings",
    origin="football-data.org",
    text=(
        "Premier League 2026/27 standings after matchweek 5.\n"
        "## Top\n1. Arsenal 13 points\n2. Liverpool 12 points"
    ),
    season="2026",
    matchweek=5,
    team_ids=(57, 64),
    date="2026-09-21",
    fetched_at=FETCHED_AT,
)
FIXTURES = Document(
    doc_id="fixtures-2026-team-64",
    title="Liverpool remaining fixtures 2026/27",
    category="fixtures",
    origin="football-data.org",
    text="Liverpool next matches.\n## Matchweek 6\nLiverpool vs Manchester City, 27 Sep 2026",
    season="2026",
    team_ids=(64, 65),
    date="2026-09-27",
    fetched_at=FETCHED_AT,
)

SAMPLE_DOCUMENTS: list[Document] = [
    trivia(1, "Who won the Ballon d'Or in 2008?", "Cristiano Ronaldo", "Ballon d'Or"),
    trivia(
        2,
        "Who scored the first ever goal in the English Premier League?",
        "Brian Deane",
        "English Premier League",
    ),
    trivia(3, "Which country won the 2010 FIFA World Cup?", "Spain", "World Cup"),
    MATCH,
    STANDINGS,
    FIXTURES,
]
SAMPLE_CHUNK_COUNT = 9
