"""Rules-only CV parsing (PRD FR-2, Design.md §4.1). Pure Python: no FastAPI, no database.

The result is a draft. The user corrects it in the confirm step (FR-3), so the rules aim to
find most fields on common Thai and English CVs, not every layout.

- Skills: taxonomy matches anywhere in the CV. A level comes only from years written next to
  the skill ("Python 4 years", "Python 2 ปี"); otherwise the user picks it.
- Sections: short heading lines such as "Experience" or "ประวัติการศึกษา".
- Dates: "Jan 2022", "06/2020", "2020", Thai months, Buddhist years (2565 → 2022),
  "Present" / "ปัจจุบัน".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.domain.matching.skills import SkillTaxonomy

WARN_NO_SKILLS = "ไม่พบทักษะที่ระบบรู้จักใน CV กรุณาเพิ่มเองในขั้นตอนยืนยัน"
WARN_NO_LEVEL = "ทักษะบางรายการยังไม่มีระดับ กรุณาเลือกระดับในขั้นตอนยืนยัน"
WARN_NO_DATES = "ไม่พบวันที่ของประสบการณ์บางรายการ"
WARN_NO_EXPERIENCE = "ไม่พบประสบการณ์ทำงานใน CV ถ้ามี กรุณาเพิ่มเองในขั้นตอนยืนยัน"
WARN_NO_EDUCATION = "ไม่พบข้อมูลการศึกษาใน CV"

SUMMARY_MAX = 500
TITLE_MAX = 150
SCHOOL_MAX = 200
MAX_EXPERIENCE = 30
MAX_EDUCATION = 20

_CONTACT = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
    r"|(?:https?://|www\.)\S+"
    r"|(?:github|gitlab|linkedin)\.com/\S*"
    r"|(?<!\d)(?:\+?66|0)[-\s]?\d{1,2}[-\s]?\d{3}[-\s]?\d{3,4}(?!\d)",
    re.IGNORECASE,
)


def without_contact(text: str) -> str:
    """Emails, links and phone numbers are never skills or facts for the LLM (FR-12, FR-22e)."""
    return re.sub(r"\s+", " ", _CONTACT.sub(" ", text)).strip()


@dataclass
class CvSkillDraft:
    name: str
    skill_id: str | None
    level: int | None
    line_no: int


@dataclass
class EducationDraft:
    school: str
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None
    line_no: int | None = None


@dataclass
class ExperienceDraft:
    title: str
    company: str | None = None
    start: str | None = None
    end: str | None = None
    months: int | None = None
    summary: str | None = None
    line_no: int | None = None


@dataclass
class ParsedCv:
    skills: list[CvSkillDraft] = field(default_factory=list)
    education: list[EducationDraft] = field(default_factory=list)
    experience: list[ExperienceDraft] = field(default_factory=list)
    warnings_th: list[str] = field(default_factory=list)


# --- sections ----------------------------------------------------------------------------

_HEADINGS = {
    "education": {
        "education",
        "academic background",
        "educational background",
        "การศึกษา",
        "ประวัติการศึกษา",
        "วุฒิการศึกษา",
    },
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "internship",
        "internships",
        "ประสบการณ์",
        "ประสบการณ์ทำงาน",
        "ประวัติการทำงาน",
        "การฝึกงาน",
    },
    "skills": {
        "skills",
        "technical skills",
        "skills and tools",
        "ทักษะ",
        "ความสามารถ",
        "ทักษะและความสามารถ",
    },
    "projects": {
        "projects",
        "project",
        "personal projects",
        "academic projects",
        "side projects",
        "โปรเจกต์",
        "โปรเจค",
        "โครงงาน",
        "โครงการ",
        "ผลงาน",
    },
    "other": {
        "certifications",
        "certificates",
        "languages",
        "awards",
        "references",
        "summary",
        "profile",
        "objective",
        "about me",
        "contact",
        "activities",
        "hobbies",
        "interests",
        "ใบรับรอง",
        "ภาษา",
        "รางวัล",
        "บุคคลอ้างอิง",
        "เกี่ยวกับฉัน",
        "ข้อมูลส่วนตัว",
        "กิจกรรม",
        "งานอดิเรก",
    },
}
_HEADING_OF = {name: section for section, names in _HEADINGS.items() for name in names}


# Project words also open ordinary lines ("โครงการ ระบบบัญชี"), so they count only on their own.
_THAI_HEADINGS = sorted(
    (
        name
        for name, section in _HEADING_OF.items()
        if re.match(r"[฀-๿]", name) and section != "projects"
    ),
    key=len,
    reverse=True,
)
SHORT_HEADING = 25


def _heading(line: str) -> str | None:
    if len(line) > 40:
        return None
    key = re.sub(r"\s+", " ", line.strip().rstrip(":").strip()).lower()
    if key in _HEADING_OF:
        return _HEADING_OF[key]
    # Designed templates join a heading and its sub-heading: "ทักษะ ทักษะซอฟต์แวร์".
    if len(key) <= SHORT_HEADING:
        for name in _THAI_HEADINGS:
            if key.startswith(name + " "):
                return _HEADING_OF[name]
    return None


def _sections(lines: list[str]) -> dict[str, list[tuple[int, str]]]:
    """Lines (1-based number, text) under each heading; text before any heading is skipped."""
    out: dict[str, list[tuple[int, str]]] = {}
    current: str | None = None
    for number, line in enumerate(lines, start=1):
        section = _heading(line)
        if section:
            current = section
            out.setdefault(section, [])
        elif current:
            out[current].append((number, line))
    return out


# --- dates -------------------------------------------------------------------------------

_EN_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_TH_MONTHS = [
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]
_TH_SHORT = [
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
]
_MONTH_WORDS = (
    [re.escape(m) for m in _TH_MONTHS + _TH_SHORT]
    + [r"(?<![a-z])" + m + r"[a-z]*\.?" for m in _EN_MONTHS]  # not "mar" in "Summary"
)
_DATE = (
    r"(?:(?P<{p}mon>" + "|".join(_MONTH_WORDS) + r")\s*)?"
    r"(?:(?P<{p}num>\d{{1,2}})\s*/\s*)?"
    r"(?P<{p}year>\d{{4}})"
)
# "ปจจุบัน" too: the same word when the PDF font lost its mark (infra.pdf_text.clean_line).
_PRESENT = r"(?P<present>present|current|now|today|ปั?จจุบั?น)"
_RANGE = re.compile(
    _DATE.format(p="s") + r"\s*(?:-|–|—|to|ถึง)\s*(?:" + _PRESENT + "|" + _DATE.format(p="e") + ")",
    re.I,
)
_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")


@dataclass(frozen=True)
class _When:
    year: int
    month: int | None

    def text(self) -> str:
        return f"{self.year:04d}-{self.month:02d}" if self.month else f"{self.year:04d}"


_ISO_MONTH = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?!\d)")
_THAI_SHORT_YEAR = re.compile(
    "(" + "|".join(re.escape(m) for m in _TH_SHORT) + r")\s*(\d{2})(?!\d)"
)


def _usual_dates(line: str) -> str:
    """Writes "2022-06" and "ม.ค. 65" in the forms `_RANGE` reads."""
    line = _ISO_MONTH.sub(r"\2/\1", line)
    return _THAI_SHORT_YEAR.sub(r"\1 25\2", line)


def _year(raw: str) -> int | None:
    year = int(raw)
    if year > 2400:  # Buddhist Era
        year -= 543
    return year if 1950 <= year <= 2100 else None


def _month(word: str | None, number: str | None) -> int | None:
    if number and 1 <= int(number) <= 12:
        return int(number)
    if not word:
        return None
    if word in _TH_MONTHS:
        return _TH_MONTHS.index(word) + 1
    if word in _TH_SHORT:
        return _TH_SHORT.index(word) + 1
    return _EN_MONTHS.index(word[:3].lower()) + 1


def _range(line: str) -> tuple[re.Match[str], _When, _When | None] | None:
    """(match, start, end); end is None for "Present"."""
    m = _RANGE.search(line)
    if not m:
        return None
    start_year = _year(m["syear"])
    if start_year is None:
        return None
    start = _When(start_year, _month(m["smon"], m["snum"]))
    if m["present"]:
        return m, start, None
    end_year = _year(m["eyear"])
    if end_year is None:
        return None
    return m, start, _When(end_year, _month(m["emon"], m["enum"]))


def _months(start: _When, end: _When | None, today: date) -> int | None:
    end = end or _When(today.year, today.month)
    if start.month is None or end.month is None:
        return None
    count = (end.year * 12 + end.month) - (start.year * 12 + start.month) + 1
    return count if count > 0 else None


def months_between(start: str | None, end: str | None, today: date) -> int | None:
    """Months between two dates in the form the draft uses; no `end` means up to today."""

    def when(text: str) -> _When | None:
        found = re.fullmatch(r"(\d{4})-(\d{2})", text.strip())
        return _When(int(found[1]), int(found[2])) if found and 1 <= int(found[2]) <= 12 else None

    first = when(start) if start else None
    last = when(end) if end else None
    if first is None or (end and last is None):
        return None
    return _months(first, last, today)


def _without(line: str, match: re.Match[str]) -> str:
    rest = line[: match.start()] + " " + line[match.end() :]
    return re.sub(r"\s+", " ", rest).strip(" -–—|,()[]:")


# --- skills ------------------------------------------------------------------------------

_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?|ปี)", re.I)


def _level(years: float) -> int:
    if years < 1:
        return 1
    if years < 3:
        return 2
    if years < 5:
        return 3
    return 4


def _skills(lines: list[str], taxonomy: SkillTaxonomy) -> list[CvSkillDraft]:
    found: dict[str, CvSkillDraft] = {}
    for number, line in enumerate(lines, start=1):
        for segment in re.split(r"[,;•|·]", without_contact(line)):
            years = _YEARS.search(segment)
            for skill_id in taxonomy.find(segment):
                level = _level(float(years[1])) if years else None
                if skill_id not in found:
                    skill = taxonomy.get(skill_id)
                    name = skill.name_en.split("(")[0].strip() if skill else skill_id
                    found[skill_id] = CvSkillDraft(name, skill_id, level, number)
                elif found[skill_id].level is None and level is not None:
                    found[skill_id].level = level
    return list(found.values())


# --- experience --------------------------------------------------------------------------

_TITLE_SPLIT = re.compile(r"\s+(?:at|@)\s+|\s*\|\s*|\s+[-–—]\s+|,\s+|\s+(?=บริษัท)|\s+ที่\s+")


def _title_company(text: str) -> tuple[str, str | None]:
    parts = _TITLE_SPLIT.split(text, maxsplit=1)
    title = parts[0].strip(" ,")[:TITLE_MAX]
    company = parts[1].strip(" ,")[:TITLE_MAX] if len(parts) > 1 and parts[1].strip(" ,") else None
    return title, company


def _experience(section: list[tuple[int, str]], today: date) -> list[ExperienceDraft]:
    entries: list[ExperienceDraft] = []
    summaries: list[list[str]] = []
    for number, raw in section:
        line = _usual_dates(without_contact(raw))
        if not line:
            continue
        found = _range(line)
        if found:
            match, start, end = found
            rest = _without(line, match)
            current = entries[-1] if entries else None
            if not rest:
                if current and current.start is None:  # title line came first, then dates
                    current.start, current.end = start.text(), end.text() if end else None
                    current.months = _months(start, end, today)
                continue
            title, company = _title_company(rest)
            entries.append(
                ExperienceDraft(
                    title=title,
                    company=company,
                    start=start.text(),
                    end=end.text() if end else None,
                    months=_months(start, end, today),
                    line_no=number,
                )
            )
            summaries.append([])
        elif not entries:
            title, company = _title_company(line)
            entries.append(ExperienceDraft(title=title, company=company, line_no=number))
            summaries.append([])
        else:
            summaries[-1].append(line)
    for entry, lines in zip(entries, summaries, strict=True):
        entry.summary = " ".join(lines)[:SUMMARY_MAX] or None
    return entries[:MAX_EXPERIENCE]


# --- education ---------------------------------------------------------------------------

_SCHOOL = re.compile(
    r"university|college|institute|school|academy|มหาวิทยาลัย|วิทยาลัย|โรงเรียน|สถาบัน", re.I
)
_DEGREE = re.compile(
    r"(Bachelor(?:'s)?(?: of [A-Z]\w*)?|Master(?:'s)?(?: of [A-Z]\w*)?|Doctor of [A-Z]\w*"
    r"|Ph\.?\s?D\.?|B\.\s?Sc\.?|B\.\s?Eng\.?|B\.\s?A\.|M\.\s?Sc\.?|M\.\s?Eng\.?|MBA|High School"
    r"|ปริญญาตรี|ปริญญาโท|ปริญญาเอก|มัธยมศึกษาตอนปลาย|ปวส\.?|ปวช\.?)"
)
_FIELD = re.compile(
    r"\s(?:in|major(?:ing)? in)\s+(.+)|สาขา(?:วิชา)?\s*(.+)|^\s*\(\s*([^)]+?)\s*\)", re.I
)
_BRACKETS = re.compile(r"\([^)]*\)")
# Outside the education section, only short lines count, so a project line that mentions a
# university is not read as a school.
EDUCATION_LINE_MAX = 60


def _strip_years(text: str) -> str:
    text = _RANGE.sub(" ", text)
    text = _YEAR.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" -–—|,()[]:")


def _education(section: list[tuple[int, str]]) -> list[EducationDraft]:
    entries: list[EducationDraft] = []
    for number, raw in section:
        line = without_contact(raw)
        school = _SCHOOL.search(line) is not None
        degree = _DEGREE.search(line)
        if not school and not degree:
            continue
        current = entries[-1] if entries else None
        if current is None or (school and current.school) or (degree and current.degree):
            current = EducationDraft(school="", line_no=number)
            entries.append(current)
        if school:
            # "( กำลังศึกษา )" and similar notes in brackets are not part of the name.
            name = _strip_years(_BRACKETS.sub(" ", line)) or _strip_years(line)
            current.school = name[:SCHOOL_MAX]
        if degree:
            current.degree = degree[1]
            after = line[degree.end() :]
            field_match = _FIELD.search(after)
            if field_match:
                current.field = _strip_years(field_match[1] or field_match[2] or field_match[3])
        found = _range(line)
        years = [y for y in (_year(raw) for raw in _YEAR.findall(line)) if y]
        if found:
            _, start, end = found
            current.start, current.end = str(start.year), str(end.year) if end else None
        elif years:
            current.end = str(years[-1])
    for entry in entries:
        if not entry.school:  # degree only: keep the line so the user can correct it
            entry.school = entry.degree or ""
    return entries[:MAX_EDUCATION]


# --- whole CV ----------------------------------------------------------------------------


def project_lines(lines: list[str]) -> list[tuple[int, str]]:
    """(1-based number, text) of each line under a projects heading."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in lines]
    return [(number, line) for number, line in _sections(lines).get("projects", []) if line]


def parse_cv(lines: list[str], taxonomy: SkillTaxonomy, *, today: date) -> ParsedCv:
    lines = [re.sub(r"\s+", " ", line).strip() for line in lines]
    sections = _sections(lines)
    parsed = ParsedCv(
        skills=_skills(lines, taxonomy),
        education=_education(sections.get("education", [])),
        experience=_experience(sections.get("experience", []), today),
    )
    if not parsed.education:  # two-column CVs: the section heading is far from its lines
        parsed.education = _education(
            [(n, line) for n, line in enumerate(lines, start=1) if len(line) <= EDUCATION_LINE_MAX]
        )
    if not parsed.skills:
        parsed.warnings_th.append(WARN_NO_SKILLS)
    elif any(s.level is None for s in parsed.skills):
        parsed.warnings_th.append(WARN_NO_LEVEL)
    if not parsed.experience:
        parsed.warnings_th.append(WARN_NO_EXPERIENCE)
    elif any(e.start is None for e in parsed.experience):
        parsed.warnings_th.append(WARN_NO_DATES)
    if not parsed.education:
        parsed.warnings_th.append(WARN_NO_EDUCATION)
    return parsed
