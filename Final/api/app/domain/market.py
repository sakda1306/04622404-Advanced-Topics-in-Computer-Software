"""Turn raw postings into the role's market data (Design.md §7, PRD FR-22, FR-22f). No I/O."""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.matching.roles import RoleProfile
from app.domain.matching.skills import SkillTaxonomy
from app.providers.base import Posting

SOURCE_TH = "JobThai (ประกาศงาน)"
TRENDING_SKILLS = 10
MIN_SKILLS_WITHOUT_TITLE = 3  # a posting with another title still fits if it asks for this many
# "Programmer" says nothing about the kind of work, so it does not rule out a more specific role.
_GENERIC_TITLE_TERMS = frozenset({"programmer", "โปรแกรมเมอร์"})
# These lead people or a business, so matching skills alone do not make them this role.
_LEVELS_NEEDING_THE_TITLE = frozenset({"manager", "lead"})
_JOB_NAMES_WITH_MANAGER = re.compile(r"(project|program|product)\s+manager|ผู้จัดการโครงการ")
# The highest level a title states wins, so "Senior Manager" is manager.
_LEVEL_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("manager", ("manager", "director", "head of", "ผู้จัดการ")),
    ("lead", ("lead", "principal", "หัวหน้า")),
    ("senior", ("senior", "sr", "ซีเนียร์", "อาวุโส")),
    ("junior", ("junior", "jr", "จูเนียร์")),
    ("intern", ("intern", "internship", "ฝึกงาน")),
)
_MIN_MONTHLY_THB = 5_000
_MAX_MONTHLY_THB = 1_000_000
_BRACKETS = re.compile(r"\([^)]*\)|（[^）]*）")
_AMOUNT = r"(\d[\d,]*(?:\.\d+)?)\s*([kK])?"
_RANGE = re.compile(rf"{_AMOUNT}(?:\s*(?:-|–|—|ถึง|to)\s*{_AMOUNT})?")
_CEILING = re.compile(r"ไม่เกิน|not over|not more than|up to|สูงสุด", re.IGNORECASE)
_SALARY_END = re.compile(r"[+;]")  # what follows is a bonus or a note, with numbers of its own
_YEARLY = re.compile(r"ต่อปี|/\s*ปี|per year|/\s*year|annual", re.IGNORECASE)
_THAI_DATE = re.compile(r"(\d{1,2})\s*([ก-๛.]+)\s*(\d{2,4})")
_THAI_MONTHS = {
    "ม.ค.": 1,
    "ก.พ.": 2,
    "มี.ค.": 3,
    "เม.ย.": 4,
    "พ.ค.": 5,
    "มิ.ย.": 6,
    "ก.ค.": 7,
    "ส.ค.": 8,
    "ก.ย.": 9,
    "ต.ค.": 10,
    "พ.ย.": 11,
    "ธ.ค.": 12,
}


@dataclass(frozen=True, slots=True)
class Salary:
    min_thb: int
    max_thb: int
    period: str  # "month" or "year"


@dataclass(frozen=True, slots=True)
class RoleSearch:
    keyword: str
    title_terms: tuple[str, ...]


@lru_cache
def load_role_search(data_dir: str) -> dict[str, RoleSearch]:
    rows = json.loads((Path(data_dir) / "role_search.json").read_text(encoding="utf-8"))
    return {
        role_id: RoleSearch(row["keyword"], tuple(row["title_terms"]))
        for role_id, row in rows.items()
    }


def is_bangkok(posting: Posting) -> bool:
    """FR-22f. The province decides; the location text is only for a posting without one."""
    place = (posting.province or posting.location).lower()
    return "กรุงเทพ" in place or "bangkok" in place


def _amount(number: str, thousands: str | None) -> int:
    return int(float(number.replace(",", "")) * (1000 if thousands else 1))


def parse_salary(text: str) -> Salary | None:
    """A range or one amount in THB. Text such as "ตามตกลง" is kept as text only (Design.md §7)."""
    # Brackets hold notes such as "(ประสบการณ์ 3 ปี)", which are not part of the amount.
    clean = _SALARY_END.split(_BRACKETS.sub(" ", text), maxsplit=1)[0]
    if _CEILING.search(clean):  # a limit says nothing about what the job actually pays
        return None
    found = _RANGE.search(clean)
    if found is None:
        return None
    low = _amount(found[1], found[2])
    high = _amount(found[3], found[4]) if found[3] else low
    period = "year" if _YEARLY.search(clean) else "month"
    scale = 12 if period == "year" else 1
    if low > high or low < _MIN_MONTHLY_THB * scale or high > _MAX_MONTHLY_THB * scale:
        return None
    return Salary(low, high, period)


def parse_posted_at(text: str) -> date | None:
    """JobThai writes Buddhist years, such as "31 ต.ค. 69"."""
    found = _THAI_DATE.search(text)
    if not found or found[2] not in _THAI_MONTHS:
        return None
    year = int(found[3])
    year = year + 1957 if year < 100 else year - 543
    try:
        return date(year, _THAI_MONTHS[found[2]], int(found[1]))
    except ValueError:
        return None


def _has_term(title: str, term: str) -> bool:
    if re.search(r"[ก-๛]", term):
        return term in title
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", title) is not None


def job_level(title: str) -> str | None:
    """The level a title states: intern, junior, senior, lead or manager. None if it states none.

    Every level stays in the cache; this only labels a posting. "Project Manager" is a job, not a
    level, so it does not count as manager.
    """
    clean = _JOB_NAMES_WITH_MANAGER.sub(" ", title.lower())
    for level, terms in _LEVEL_TERMS:
        if any(_has_term(clean, term) for term in terms):
            return level
    return None


def _names_another_role(title: str, role: RoleProfile, searches: dict[str, RoleSearch]) -> bool:
    return any(
        _has_term(title, term)
        for role_id, other in searches.items()
        if role_id != role.role_id
        for term in other.title_terms
        if term not in _GENERIC_TITLE_TERMS
    )


def fits_role(
    posting: Posting, role: RoleProfile, searches: dict[str, RoleSearch], taxonomy: SkillTaxonomy
) -> bool:
    """The title names the role, or names no other role and asks for its required skills."""
    title = posting.title.lower()
    if any(_has_term(title, term) for term in searches[role.role_id].title_terms):
        return True
    if _names_another_role(title, role, searches):
        return False
    if job_level(posting.title) in _LEVELS_NEEDING_THE_TITLE:
        return False
    found = set(taxonomy.find(f"{posting.title}\n{posting.text}"))
    wanted = sum(1 for need in role.required if found.intersection(need.skills))
    return wanted >= min(MIN_SKILLS_WITHOUT_TITLE, len(role.required))


def demand(postings: Sequence[Posting], taxonomy: SkillTaxonomy) -> dict[str, Any]:
    """The posting count and the skills asked for most often (Design.md §7)."""
    counts: Counter[str] = Counter()
    for posting in postings:
        counts.update(taxonomy.find(f"{posting.title}\n{posting.text}"))
    trending = []
    for skill_id, count in counts.most_common():
        skill = taxonomy.get(skill_id)
        if skill is not None and skill.type == "hard":
            trending.append({"skill_id": skill_id, "name_th": skill.name_th, "count": count})
    return {"posting_count": len(postings), "trending_skills": trending[:TRENDING_SKILLS]}


def advertised_range(salaries: Sequence[Salary], as_of: date) -> dict[str, Any] | None:
    """A typical monthly range: the median low and the median high, so one outlier cannot set it.

    Yearly figures stay out of it, because they may include bonuses.
    """
    monthly = [salary for salary in salaries if salary.period == "month"]
    if not monthly:
        return None
    return {
        "min_thb": round(statistics.median(salary.min_thb for salary in monthly)),
        "max_thb": round(statistics.median(salary.max_thb for salary in monthly)),
        "measure": "monthly_base",
        "source": SOURCE_TH,
        "source_type": "advertised",
        "sample_size": len(monthly),
        "as_of": as_of.isoformat(),
    }
