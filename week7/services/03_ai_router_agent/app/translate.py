"""Multi-query: an English search query for a Thai question, checked before it is used.

The trivia and match documents are English. A Thai question searched as typed misses many of
them, so the router also searches an English rewrite and fuses both result lists (RRF). The
rewrite is only a search query: it may not bring in a team or a number the question lacks.
"""

import os
import re

from .teams import TeamDirectory


THAI = re.compile(r"[ก-๙]")
NUMBER = re.compile(r"\d+")
CITATION = re.compile(r"\[\d+\]")
DISABLED_VALUES = ("false", "0", "no", "off")
RRF_K = 60


def multi_query_enabled() -> bool:
    return os.getenv("ROUTER_MULTI_QUERY_ENABLED", "true").strip().lower() not in DISABLED_VALUES


def needs_translation(text: str) -> bool:
    return bool(THAI.search(text))


def validate_translation(source: str, english: str, teams: TeamDirectory) -> str | None:
    """The English query, or None when its teams differ from the question's or it adds a number.

    Time words are not checked: "เมื่อวาน" becoming "yesterday" is the translation working.
    """
    candidate = english.strip()
    if not candidate or len(candidate) > 3 * len(source.strip()) + 120 or CITATION.search(candidate):
        return None
    known = {team.team_id for team in teams.find(source)}
    named = {team.team_id for team in teams.find(candidate)}
    # An added team pulls other clubs' documents in; a dropped one ("Did they win?") lets any
    # document in. Either way the fused top 5 could carry chunks the question is not about.
    if named != known:
        return None
    if set(NUMBER.findall(candidate)) - set(NUMBER.findall(source)):
        return None
    return candidate


def fuse(base: list[dict], extra: list[dict], k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion of two /search results by chunk_id; ties keep base order first."""
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}
    for results in (base, extra):
        for rank, chunk in enumerate(results, start=1):
            key = str(chunk.get("chunk_id") or chunk.get("text"))
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(key, chunk)
    order = {key: index for index, key in enumerate(chunks)}
    return [chunks[key] for key in sorted(scores, key=lambda key: (-scores[key], order[key]))]
