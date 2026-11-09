"""What the router decides for one chat message (Design.md §4.6, Contract.md §2.4)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ANSWER_ROUTES = (
    "skill_assessment",
    "work_style",
    "blind_spots",
    "job_matching",
    "salary",
    "market",
    "experience",
    "profile_edit",
)
_ZERO_WIDTH = re.compile("[\u200b-\u200d\u2060\ufeff]")


@dataclass(frozen=True, slots=True)
class Decision:
    route: str
    confidence: float
    layer: str  # guard, rules or llm
    tokens: int = 0


def normalize(message: str) -> str:
    """The form guards and rules read: hidden characters and spelling variants removed."""
    text = unicodedata.normalize("NFKC", _ZERO_WIDTH.sub("", message))
    # NFKC splits sara am, and many keyboards type it split: always use the one character.
    text = text.replace("\u0e4d\u0e32", "\u0e33")
    return " ".join(text.casefold().split())
