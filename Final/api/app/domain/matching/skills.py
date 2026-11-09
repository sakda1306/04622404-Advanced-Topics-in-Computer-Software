"""Skill taxonomy from `data/skills.json` and matching in free text (Design.md §2.1).

Match terms per skill: the English name (and the names in its brackets), the Thai name,
and the aliases. Aliases come in three forms in the data:
- plain words, such as "apache spark" (spaces and hyphens in the text may vary);
- joined words, such as "amazonwebservices", matched against the line without spaces;
- two regex patterns, such as "c(?![#+])", used as written.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# Short terms that are also everyday English words; they match only in capitals ("AI", "UI").
_CAPITALS_ONLY = frozenset(
    {"ai", "ids", "rag", "sap", "ui", "ux", "ml", "iam", "lan", "wan", "esb", "mdm"}
)
_REGEX_CHARS = re.compile(r"[()?|\\\[\]]")
# A skill term is not part of a longer English word: no Latin letter, digit, "+" or "#" right
# next to it. Thai letters may touch it, because Thai CVs often write "ใช้Python".
_LEFT = r"(?<![A-Za-z0-9+#])"
_RIGHT = r"(?![A-Za-z0-9+#])"
_THAI = re.compile(r"[฀-๿]")
_MIN_CLOSE_NAME = 5
_CLOSE_CUTOFF = 0.8
_MIN_SUGGESTED_NAME = 3


@dataclass(frozen=True, slots=True)
class SkillDef:
    id: str
    name_en: str
    name_th: str
    type: str  # "hard" or "soft"
    category: str


@dataclass(frozen=True, slots=True)
class _Matcher:
    skill_id: str
    pattern: re.Pattern[str]
    joined: bool = False  # match against the line without spaces


def _english_names(name_en: str) -> list[str]:
    main, _, rest = name_en.partition("(")
    names = [main]
    for part in re.split(r"[,/]", rest.rstrip(")")):
        part = re.sub(r"\betc\.?", "", part).strip()
        if part:
            names.append(part)
    return [n.strip() for n in names if n.strip()]


def _plain(term: str) -> str:
    words = re.split(r"[\s\-]+", term.strip())
    return r"[\s\-]*".join(re.escape(w) for w in words if w)


def _matchers(skill: SkillDef, aliases: list[str]) -> list[_Matcher]:
    out: list[_Matcher] = []
    has_regex = any(_REGEX_CHARS.search(a) for a in aliases)
    terms = [] if has_regex else _english_names(skill.name_en)  # "C", "R": only the pattern
    for term in terms + [a for a in aliases if not _REGEX_CHARS.search(a)]:
        lowered = term.lower()
        if lowered in _CAPITALS_ONLY:
            out.append(_Matcher(skill.id, re.compile(_LEFT + re.escape(term.upper()) + _RIGHT)))
        elif " " not in term and "-" not in term and len(term) >= 12 and term.isalpha():
            out.append(_Matcher(skill.id, re.compile(re.escape(lowered)), joined=True))
        else:
            out.append(_Matcher(skill.id, re.compile(_LEFT + _plain(lowered) + _RIGHT, re.I)))
    for alias in aliases:
        if _REGEX_CHARS.search(alias):
            out.append(_Matcher(skill.id, re.compile(_LEFT + alias + _RIGHT, re.I)))
    thai_main = skill.name_th.split("(")[0].strip()
    if _THAI.search(thai_main) and len(thai_main) >= 4:
        out.append(_Matcher(skill.id, re.compile(re.escape(thai_main))))  # Thai has no spaces
    return out


class SkillTaxonomy:
    def __init__(self, skills: list[SkillDef], aliases: dict[str, list[str]]) -> None:
        self._skills = {s.id: s for s in skills}
        self._matchers = [m for s in skills for m in _matchers(s, aliases.get(s.id, []))]
        self._names = {
            name.lower(): s.id
            for s in skills
            for name in _english_names(s.name_en)
            if len(name) >= _MIN_CLOSE_NAME
        }
        self._spellings: dict[str, str] = {}
        for s in skills:
            plain = [a for a in aliases.get(s.id, []) if not _REGEX_CHARS.search(a)]
            for name in [*_english_names(s.name_en), s.name_th.split("(")[0], *plain]:
                self._spellings.setdefault(name.strip().lower(), s.id)

    @classmethod
    def from_file(cls, path: Path) -> SkillTaxonomy:
        rows = json.loads(path.read_text(encoding="utf-8"))
        skills = [
            SkillDef(r["id"], r["name_en"], r["name_th"], r["type"], r["category"]) for r in rows
        ]
        return cls(skills, {r["id"]: list(r.get("aliases", [])) for r in rows})

    def get(self, skill_id: str) -> SkillDef | None:
        return self._skills.get(skill_id)

    def __contains__(self, skill_id: object) -> bool:
        return skill_id in self._skills

    def closest(self, name: str) -> str | None:
        """A mistyped skill name, "Pyhton". Long names only: a short word must not match a skill."""
        if len(name) < _MIN_CLOSE_NAME:
            return None
        found = difflib.get_close_matches(name.lower(), self._names, n=1, cutoff=_CLOSE_CUTOFF)
        return self._names[found[0]] if found else None

    def suggest(self, name: str) -> str | None:
        """The skill a person probably meant, to ask them about. Wider than `closest`: never score
        on this without asking. Reads Thai names and aliases too, and shorter words."""
        wanted = name.strip().lower()
        if len(wanted) < _MIN_SUGGESTED_NAME:
            return None
        found = difflib.get_close_matches(wanted, self._spellings, n=1, cutoff=_CLOSE_CUTOFF)
        return self._spellings[found[0]] if found else None

    def find(self, line: str) -> list[str]:
        """Skill ids mentioned in one line, in taxonomy order, each once."""
        lowered = line.lower()
        joined = re.sub(r"[\s\-]+", "", lowered)
        found: dict[str, None] = {}
        for m in self._matchers:
            if m.skill_id in found:
                continue
            if m.pattern.search(joined if m.joined else line):
                found[m.skill_id] = None
        return list(found)


@lru_cache
def load_taxonomy(data_dir: str) -> SkillTaxonomy:
    return SkillTaxonomy.from_file(Path(data_dir) / "skills.json")
