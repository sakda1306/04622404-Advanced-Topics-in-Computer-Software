"""Knowledge Base documents, their doc_id rules (CONTRACT §6) and chunks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

CATEGORIES = (
    "trivia",
    "match_report",
    "standings",
    "fixtures",
    "weekly_report",
    "player",
    "historical",
)
ORIGINS = ("kb", "football-data.org", "api-football", "generated", "openfootball", "fjelstul")

# Locked in CONTRACT §6: upserting the same doc_id replaces the document, so no duplicates.
DOC_ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "trivia": re.compile(r"trivia-\d{4}"),
    "match_report": re.compile(r"match-\d{4}-mw\d{2}-\d+-\d+"),
    # One current snapshot per season; legacy IDs remain valid during cleanup.
    "standings": re.compile(r"standings-\d{4}(?:-mw\d{2})?"),
    "fixtures": re.compile(r"fixtures-\d{4}-team-\d+"),
    "weekly_report": re.compile(r"weekly-\d{4}-mw\d{2}"),
    # v1.16: one head coach document per team from Wikidata.
    "player": re.compile(r"(?:players|coach)-\d{4}-team-\d+"),
    # v1.11: 07's Premier League archive; club slugs are lowercase words joined by hyphens.
    # v1.13: club records and the league honours document.
    "historical": re.compile(
        r"hist-(?:season-\d{4}|team-\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*|h2h-[a-z0-9]+(?:-[a-z0-9]+)*"
        r"|club-[a-z0-9]+(?:-[a-z0-9]+)*|records)"
    ),
}


def doc_id_matches(category: str, doc_id: str) -> bool:
    pattern = DOC_ID_PATTERNS.get(category)
    return bool(pattern and pattern.fullmatch(doc_id))


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    title: str
    category: str
    origin: str
    text: str
    season: str | None = None
    matchweek: int | None = None
    team_ids: tuple[int, ...] = ()
    date: str | None = None
    fetched_at: str | None = None
    url: str | None = None
    # Original trivia category (World Cup, Ballon d'Or, ...); optional extra field (§0).
    topic: str | None = None

    def content_hash(self) -> str:
        """Changes when any field changes; an unchanged document is not embedded again."""
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    ord: int
    text: str
    bm25_text: str
