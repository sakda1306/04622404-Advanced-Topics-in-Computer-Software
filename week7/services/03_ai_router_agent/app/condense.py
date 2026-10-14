"""Decide when a follow-up question needs an LLM rewrite and check that rewrite.

A rewrite is only used for routing and retrieval. It may not bring in a team, a
number or a time scope that the user's question and the chat history do not
already contain, and it may not drop a team the user named.
"""

import os
import re

from .decisions import _intent
from .teams import Team, TeamDirectory


TEAM_FREE_INTENTS = {"standings_stats", "weekly_summary", "trivia_history", "general_football"}
# Intents whose rules-layer decision is complete once the team is known (trivia rules misfire too often).
TEAM_BOUND_INTENTS = {"match_result", "fixture_schedule", "standings_stats", "player_info"}
SHORT_QUERY_CHARS = 15
# Thai has no spaces, so short nicknames (ผี, ปืน, หงส์) also match inside other words.
MIN_THAI_ALIAS_CHARS = 5
FOLLOWUP_TH = re.compile(r"^แล้ว|เขา|นัดนั้น|ทีมนี้|ทีมนั้น|คนนั้น|นัดก่อน|นัดต่อไป|อีกทีม|ล่ะ\s*\??$")
FOLLOWUP_EN_OPENER = re.compile(r"^(?:and|what about|how about)\b", re.IGNORECASE)
FOLLOWUP_EN_PRONOUN = re.compile(r"\b(?:he|she|him|his|her|they|them|their|it|its|that|those)\b", re.IGNORECASE)
QUESTION_TH = re.compile(r"ไหม|มั้ย|อะไร|ใคร|เท่าไหร่|ยังไง|อย่างไร|กี่|ที่ไหน|ไหน|เมื่อไหร่|บ้าง|ล่ะ|หรือเปล่า")
QUESTION_EN = re.compile(r"^(?:who|what|when|where|which|why|how|is|are|was|were|did|does|do|can|will)\b",
                         re.IGNORECASE)
THAI = re.compile(r"[ก-๙]")
CITATION = re.compile(r"\[\d+\]")
NUMBER = re.compile(r"\d+")
NUMBER_WORDS_TH = ("หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า", "สิบ", "ยี่สิบ", "ร้อย")
NUMBER_WORDS_EN = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|first|second|third|fourth|fifth|sixth|seventh|"
    r"eighth|ninth|tenth)\b", re.IGNORECASE)
# Time scopes change which season or day the answer is about, so a rewrite may not add one.
TIME_MARKERS_TH = ("ฤดูกาลที่แล้ว", "ซีซั่นที่แล้ว", "ปีที่แล้ว", "ฤดูกาลก่อน", "ซีซั่นก่อน", "ตลอดกาล",
                   "ประวัติศาสตร์", "ย้อนหลัง", "เมื่อวาน", "วันนี้", "พรุ่งนี้", "สัปดาห์นี้",
                   "สัปดาห์ที่แล้ว", "นัดล่าสุด", "นัดก่อน", "นัดต่อไป")
TIME_MARKERS_EN = re.compile(r"\b(?:last season|previous season|all[- ]time|ever|in history|yesterday|today|"
                             r"tomorrow|this week|last week)\b", re.IGNORECASE)
DISABLED_VALUES = ("false", "0", "no", "off")


def condense_enabled() -> bool:
    return os.getenv("ROUTER_CONDENSE_ENABLED", "true").strip().lower() not in DISABLED_VALUES


def _content(item: dict) -> str:
    return str(item.get("content") or "")


def rules_resolved(decision) -> bool:
    """The rules already chose a team-bound intent and its team, so a rewrite cannot improve routing."""
    return (decision is not None and decision.layer == "rules" and decision.route != "clarify"
            and decision.intent in TEAM_BOUND_INTENTS and bool(decision.team_ids))


def needs_condense(query: str, history: list[dict], teams: TeamDirectory, season: str | None = None) -> bool:
    if not any(item.get("role") == "user" and _content(item).strip() for item in history):
        return False
    text = query.strip()
    if FOLLOWUP_TH.search(text) or FOLLOWUP_EN_OPENER.search(text) or len(text) < SHORT_QUERY_CHARS:
        return True
    if teams.find(text):
        return False
    return bool(FOLLOWUP_EN_PRONOUN.search(text)) or _intent(text, season) not in TEAM_FREE_INTENTS


def _is_question(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith("?") or bool(QUESTION_TH.search(stripped) or QUESTION_EN.search(stripped))


def _strict(teams: TeamDirectory) -> TeamDirectory:
    return TeamDirectory([Team(team.team_id, team.name, team.short_name,
                               tuple(alias for alias in team.aliases
                                     if alias.isascii() or len(alias) >= MIN_THAI_ALIAS_CHARS))
                          for team in teams.teams])


def _numbers(text: str) -> set[str]:
    return (set(NUMBER.findall(text)) | {word for word in NUMBER_WORDS_TH if word in text}
            | {match.lower() for match in NUMBER_WORDS_EN.findall(text)})


def _time_markers(text: str) -> set[str]:
    return ({marker for marker in TIME_MARKERS_TH if marker in text}
            | {match.lower() for match in TIME_MARKERS_EN.findall(text)})


def invented_entities(original: str, rewritten: str, history: list[dict], teams: TeamDirectory) -> list[str]:
    """Teams, numbers and time scopes in the rewrite that appear in neither the question nor the history."""
    source = "\n".join([original, *(_content(item) for item in history)])
    known = {team.team_id for team in _strict(teams).find(source)}
    names = [team.short_name for team in teams.find(rewritten) if team.team_id not in known]
    numbers = sorted(_numbers(rewritten) - _numbers(source))
    times = sorted(_time_markers(rewritten) - _time_markers(source))
    return names + numbers + times


def validate(original: str, rewritten: str, history: list[dict], teams: TeamDirectory) -> str | None:
    candidate = rewritten.strip()
    if not candidate or len(candidate) > 3 * len(original.strip()) + 120:
        return None
    if CITATION.search(candidate):
        return None
    # The rules read Thai questions; a rewrite in the other language would route differently.
    if bool(THAI.search(original)) != bool(THAI.search(candidate)):
        return None
    if _is_question(original) and not _is_question(candidate):
        return None
    if invented_entities(original, candidate, history, teams):
        return None
    asked = {team.team_id for team in teams.find(original)}
    if not asked <= {team.team_id for team in teams.find(candidate)}:
        return None
    return candidate
