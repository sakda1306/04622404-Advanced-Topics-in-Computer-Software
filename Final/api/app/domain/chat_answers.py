"""Build chat answers from computed data (Design.md §4.6, PRD FR-12, FR-16, FR-17).

Pure Python. Scores, gaps, months and salary figures always come from here; the LLM only words
claims, which `parse_claims` checks before they reach `claim_lines`.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.market import SOURCE_TH
from app.domain.matching.roles import RoleProfile
from app.domain.matching.skills import SkillTaxonomy
from app.rag.chunking import Chunk

NO_ROLE_TH = "อยากรู้เงินเดือนของตำแหน่งไหนครับ เช่น QA Engineer หรือ Data Analyst"
NO_MARKET_ROLE_TH = "อยากรู้ตลาดงานของตำแหน่งไหนครับ เช่น QA Engineer หรือ Data Analyst"
MARKET_STALE_TH = "ข้อมูลนี้อาจไม่เป็นปัจจุบัน"
REFERENCE_NOTE_TH = "ตารางอ้างอิงจัดทำโดยทีมผู้พัฒนา ไม่ใช่ตัวเลขจากประกาศงาน"
MATCH_NOTE_TH = "คำนวณจากทักษะที่ตรงกับสายงาน ไม่ใช่การรับประกันการได้งาน"
NO_BLIND_SPOTS_TH = "จากข้อมูลตอนนี้ยังไม่พบจุดที่ควรระวังเป็นพิเศษครับ"
NO_EXPERIENCE_TH = "ในโปรไฟล์ยังไม่มีข้อมูลประสบการณ์ครับ"
NO_SKILLS_TH = "ในโปรไฟล์ยังไม่มีข้อมูลทักษะครับ"
LEVEL_MEANING_TH = "1 พื้นฐาน, 2 ใช้งานได้, 3 เก่ง, 4 เชี่ยวชาญ"

_LEVELS_TH = {"entry": "ระดับเริ่มต้น", "junior": "ระดับจูเนียร์"}
_MONTHS_TH = (
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
)
_BUDDHIST_YEARS = 543
_MAX_ROLES = 3
_MAX_GAPS_SHOWN = 3
_MAX_SKILLS_SHOWN = 5
_MAX_NOTE_CHARS = 600  # bounds the tokens of one call
_DRAFT_NOTE_TH = "ร่างจากทีมผู้พัฒนา ยังไม่ได้ตรวจทาน"
_TWO_PART_WORD = re.compile(r"\b(full|front|back)[\s-]+(stack|end)\b")
# The names people type, in the form `_normalized` gives. Two letters alone ("de", "da") are too
# likely to be something else.
_ROLE_ALIASES = {
    "backend-developer": ("แบคเอนด์", "แบ็คเอนด์", "แบ็กเอนด์"),
    "frontend-developer": ("ฟรอนต์เอนด์", "ฟรอนท์เอนด์", "ฟร้อนท์เอนด์", "ฟรอนเอนด์"),
    "fullstack-developer": ("ฟูลสแตก", "ฟูลสแตค", "ฟูลแสต็ค"),
    "mobile-developer": ("mobile dev", "แอปมือถือ"),
    "software-engineer": ("programmer", "โปรแกรมเมอร์", "software dev"),
    "qa-engineer": ("เทสเตอร์", "นักทดสอบ", "ทดสอบซอฟต์แวร์"),
    "devops-engineer": ("เดฟออปส์",),
    "data-engineer": ("data eng", "ดาต้าเอนจิเนียร์"),
    "data-scientist": ("data sci", "ดาต้าไซเอนซ์", "ดาต้าไซแอนทิสต์"),
    "data-analyst": ("ดาต้าอนาลิสต์", "ดาต้าแอนะลิสต์"),
    "information-security-analyst": ("cyber", "cybersecurity", "ไซเบอร์"),
    "ux-ui-designer": ("uxui", "ux ui", "ux/ui"),
    "it-project-manager": ("project manager",),
}
_FOLLOW_UP = re.compile(r"^(?:แล้ว|ส่วน|ทำไม|ขยาย|ต่อ|and\b|what about\b|why\b)")
_YES_OR_NO = re.compile(r"ไหม|มั้ย|หรือเปล่า|รึเปล่า")
_DESIRED_SALARY = re.compile(r"ที่(?:ฉัน|ผม|เรา|หนู)?\s*(?:อยากได้|ต้องการ|คาดหวัง)")
_BY_YEARS = re.compile(r"\d+\s*ปี|\d+\s*years?|ประสบการณ์")
_COMPARES = re.compile(r"ต่างกัน|เทียบ|compare|difference")
_ASKS_COMPANIES = re.compile(r"บริษัท|รับสมัคร|ที่ไหน|company|companies")
_MAX_LISTINGS_SHOWN = 5
_NAMED_THING = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]+")
_ADVICE_TO_LEARN = re.compile(r"เรียน|ฝึก|เริ่ม|ต่อด้วย|ถัดไป|สุดท้าย|พัฒนา|ปรับปรุง|เก็บทักษะ|ควร|ลำดับ")
ASKED_ROLES_HEADING_TH = "สายงานที่คุณถามถึง:"
CANNOT_JUDGE_TH = "ยังตัดสินเรื่องนี้โดยตรงไม่ได้ครับ ข้อมูลที่มีคือ:"
ROUGH_FIGURE_TH = "ตัวเลขนี้เป็นค่าโดยรวมของสายงาน ไม่ได้แยกตามจำนวนปีประสบการณ์"
FEW_POSTINGS_TH = "ตัวเลขจากประกาศมาจากจำนวนไม่มาก จึงอาจต่างจากตารางอ้างอิงเงินเดือน"


@dataclass(frozen=True, slots=True)
class SalaryRow:
    role_id: str
    min_thb: int
    max_thb: int
    level: str
    match: str
    source: str
    url: str
    published_at: str


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0


class Citations:
    """Numbers evidence by first use, so the same evidence keeps one number."""

    def __init__(self, evidence: Mapping[str, Mapping[str, Any]]) -> None:
        self._evidence = evidence
        self.sources: list[dict[str, Any]] = []

    def mark(self, evidence_ids: Iterable[str]) -> str:
        numbers = [self._number(i) for i in evidence_ids if i in self._evidence]
        return " ".join(f"[{n}]" for n in dict.fromkeys(numbers))

    def _number(self, evidence_id: str) -> int:
        for source in self.sources:
            if source["evidence_id"] == evidence_id:
                return int(source["n"])
        found = self._evidence[evidence_id]
        source = {
            "n": len(self.sources) + 1,
            "evidence_id": evidence_id,
            "label_th": found["label_th"],
        }
        if found.get("url"):
            source["url"] = found["url"]
        self.sources.append(source)
        return int(source["n"])


def _normalized(text: str) -> str:
    return _TWO_PART_WORD.sub(r"\1\2", text.casefold())


def _words(role: RoleProfile) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalized(f"{role.role_id} {role.title_en}")))


def _span(text: str, role: RoleProfile, own_words: set[str]) -> tuple[int, int] | None:
    """Where the message first names the role; "ui" must not count inside "required"."""
    names = [_normalized(name).strip() for name in role.title_en.split("/")]
    names.extend(name.strip() for name in _normalized(role.title_th).split("/"))
    names.extend(_ROLE_ALIASES.get(role.role_id, ()))
    spans = []
    for name in {*names, *own_words}:
        found = name and re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text)
        if found:
            spans.append(found.span())
    return min(spans, key=lambda span: (span[0], -span[1])) if spans else None


def find_roles(message: str, catalogue: Sequence[RoleProfile]) -> list[str]:
    """Roles the message names, first named first: a full name, or a word only that role uses."""
    text = _normalized(message)
    words = {role.role_id: _words(role) for role in catalogue}
    found: list[tuple[int, int, str]] = []
    for role in catalogue:
        others = set().union(*(w for rid, w in words.items() if rid != role.role_id))
        span = _span(text, role, words[role.role_id] - others)
        if span is not None:
            found.append((*span, role.role_id))
    # "ผู้ดูแลระบบ" inside "ผู้ดูแลระบบฐานข้อมูล" names only the longer role.
    kept = [
        (start, role_id)
        for start, end, role_id in found
        if not any(
            s <= start and end <= e and e - s > end - start
            for s, e, other in found
            if other != role_id
        )
    ]
    return [role_id for _, role_id in sorted(kept)[:_MAX_ROLES]]


@lru_cache
def load_salary_reference(data_dir: str) -> dict[str, SalaryRow]:
    path = Path(data_dir) / "salary" / "reference.csv"
    with path.open(encoding="utf-8", newline="") as file:
        return {
            row["role_id"]: SalaryRow(
                role_id=row["role_id"],
                min_thb=int(row["min"]),
                max_thb=int(row["max"]),
                level=row["level"],
                match=row["match"],
                source=row["source"],
                url=row["url"],
                published_at=row["published_at"],
            )
            for row in csv.DictReader(file)
        }


def _thai_date(iso_date: str) -> str:
    day = date.fromisoformat(iso_date)
    return f"{day.day} {_MONTHS_TH[day.month - 1]} {day.year + _BUDDHIST_YEARS}"


def _role_name(role: RoleProfile) -> str:
    return f"{role.title_th} ({role.title_en})"


def salary_answer(
    role_ids: Sequence[str],
    rows: Mapping[str, SalaryRow],
    roles: Mapping[str, RoleProfile],
) -> Answer:
    evidence = {
        f"salary-{r.role_id}": {
            "label_th": f"{r.source}, {_thai_date(r.published_at)}",
            "url": r.url,
        }
        for r in rows.values()
    }
    cites = Citations(evidence)
    lines: list[str] = []
    for role_id in role_ids:
        name = _role_name(roles[role_id])
        row = rows.get(role_id)
        if row is None:
            lines.append(f"{name}: ยังไม่มีข้อมูลเงินเดือนในตารางอ้างอิงครับ")
            continue
        level = _LEVELS_TH.get(row.level, row.level)
        amount = f"฿{row.min_thb:,} – ฿{row.max_thb:,} / เดือน (ฐานเงินเดือน)"
        mark = cites.mark([f"salary-{role_id}"])
        lines.append(f"{name}: {amount}, {level} {mark}")
        lines.append(f"ที่มา: {row.source}, {_thai_date(row.published_at)}")
        if row.match == "proxy":
            lines.append("ตัวเลขนี้อ้างอิงจากตำแหน่งใกล้เคียง")
    if cites.sources:
        lines.append(REFERENCE_NOTE_TH)
    return Answer(text="\n".join(lines), sources=cites.sources)


def _market_lines(name: str, market: Mapping[str, Any], mark: str) -> list[str]:
    count = market["demand"]["posting_count"]
    found = f"พบ {count} ประกาศ" if count else "รอบล่าสุดไม่พบประกาศที่ตรงกับตำแหน่งนี้"
    lines = [f"{name} (ข้อมูลกรุงเทพฯ): {found} {mark}"]
    skills = market["demand"]["trending_skills"][:_MAX_SKILLS_SHOWN]
    if skills:
        wanted = ", ".join(f"{s['name_th']} {s['count']} ประกาศ" for s in skills)
        lines.append(f"ทักษะที่ประกาศระบุมากที่สุด: {wanted}")
    advertised = market["salary"]["advertised"]
    if advertised:
        amount = f"฿{advertised['min_thb']:,} – ฿{advertised['max_thb']:,} / เดือน (ฐานเงินเดือน)"
        lines.append(f"เงินเดือนในประกาศ: {amount} จาก {advertised['sample_size']} ประกาศ")
        lines.append(FEW_POSTINGS_TH)
    if market["stale"]:
        lines.append(MARKET_STALE_TH)
    return lines


def market_answer(
    role_ids: Sequence[str],
    markets: Mapping[str, Mapping[str, Any]],
    roles: Mapping[str, RoleProfile],
    *,
    postings_per_role: int,
) -> Answer:
    """`markets` holds Contract.md `RoleMarket` values. The count is a capped sample and says so."""
    evidence = {
        f"market-{role_id}": {
            "label_th": f"{SOURCE_TH}, อัปเดตล่าสุด {_thai_date(market['fetched_at'][:10])}"
        }
        for role_id, market in markets.items()
        if market["available"]
    }
    cites = Citations(evidence)
    lines: list[str] = []
    for role_id in role_ids:
        name = _role_name(roles[role_id])
        market = markets[role_id]
        if not market["available"]:
            lines.append(f"{name}: ยังไม่มีข้อมูลประกาศงานครับ")
            continue
        mark = cites.mark([f"market-{role_id}"])
        lines.extend(_market_lines(name, market, mark))
        lines.append(f"ที่มา: {evidence[f'market-{role_id}']['label_th']}")
    if cites.sources:
        lines.append(
            f"จำนวนนี้มาจากประกาศที่ดึงมาไม่เกิน {postings_per_role} รายการต่อตำแหน่ง "
            "ไม่ใช่จำนวนงานที่เปิดรับทั้งหมด"
        )
        lines.append(markets[role_ids[0]]["disclaimer_th"])
    return Answer(text="\n".join(lines), sources=cites.sources)


def is_follow_up(message: str) -> bool:
    return _FOLLOW_UP.search(_normalized(message).strip()) is not None


def is_yes_or_no(message: str) -> bool:
    return _YES_OR_NO.search(message) is not None


def asks_desired_salary(message: str) -> bool:
    return _DESIRED_SALARY.search(message) is not None


def asks_companies(message: str) -> bool:
    return _ASKS_COMPANIES.search(_normalized(message)) is not None


def desired_salary_line(amount: int) -> str:
    return f"เงินเดือนที่คุณต้องการในโปรไฟล์คือ ฿{amount:,} / เดือน"


def salary_notes(message: str, role_ids: Sequence[str], rows: Mapping[str, SalaryRow]) -> list[str]:
    """What the question asked beyond the range: a split by years, or the gap between two roles."""
    lines: list[str] = []
    known = [rows[role_id] for role_id in role_ids if role_id in rows]
    if _BY_YEARS.search(_normalized(message)):
        lines.append(ROUGH_FIGURE_TH)
    if _COMPARES.search(_normalized(message)) and len(known) >= 2:
        first, second = known[0], known[1]
        low = abs(first.min_thb - second.min_thb)
        high = abs(first.max_thb - second.max_thb)
        lines.append(f"เมื่อเทียบกัน ขั้นต่ำต่างกัน ฿{low:,} และขั้นสูงต่างกัน ฿{high:,} ต่อเดือน")
    return lines


def listing_lines(name: str, listings: Sequence[Mapping[str, Any]]) -> list[str]:
    companies = list(dict.fromkeys(item["company"] for item in listings if item.get("company")))
    if not companies:
        return []
    return [f"บริษัทที่เปิดรับ {name} จากประกาศล่าสุด: {', '.join(companies)}"]


def role_requirements(
    role: RoleProfile, profile: Mapping[str, Any], taxonomy: SkillTaxonomy
) -> list[dict[str, Any]]:
    """Each required skill against the user's level, worked out here and not left to the LLM."""
    levels = {s["skill_id"]: s["level"] for s in profile["hard_skills"]}
    out: list[dict[str, Any]] = []
    for need in role.required:
        names = [
            known.name_th if (known := taxonomy.get(skill_id)) else skill_id
            for skill_id in need.skills
        ]
        have = [levels[skill_id] for skill_id in need.skills if skill_id in levels]
        user_level = max(have) if have else None
        item = {
            "name": " / ".join(names),
            "required_level": need.min_level,
            "user_level": user_level,
            "enough": user_level is not None and user_level >= need.min_level,
        }
        out.append(item)
    return out


def asked_role_facts(
    role: RoleProfile,
    match: Mapping[str, Any],
    profile: Mapping[str, Any],
    taxonomy: SkillTaxonomy,
) -> dict[str, Any]:
    return {
        **_role_facts(match),
        "title_en": role.title_en,
        "required": role_requirements(role, profile, taxonomy),
    }


def role_fit_lines(
    role: RoleProfile,
    match: Mapping[str, Any],
    profile: Mapping[str, Any],
    taxonomy: SkillTaxonomy,
    cites: Citations,
) -> list[str]:
    mark = cites.mark([f"role-{role.role_id}"])
    lines = [f"สาย {role.title_th} ตรงกับคุณ {match['match_pct']}% {mark}".rstrip()]
    for need in role_requirements(role, profile, taxonomy):
        if need["user_level"] is None:
            lines.append(f"- {need['name']}: ยังไม่มีในโปรไฟล์ (ต้องการระดับ {need['required_level']})")
            continue
        verdict = "พอแล้ว" if need["enough"] else "ยังต่ำกว่าที่ต้องการ"
        lines.append(
            f"- {need['name']}: ระดับ {need['user_level']} ต้องการ {need['required_level']} {verdict}"
        )
    return lines


def values_text(facts: Any) -> str:
    """The values alone: a field name such as "required_level" is not something to tell a user."""
    if isinstance(facts, Mapping):
        return " ".join(values_text(value) for value in facts.values())
    if isinstance(facts, list | tuple):
        return " ".join(values_text(value) for value in facts)
    return str(facts)


def supported_claims(
    claims: Sequence[dict[str, Any]],
    *,
    facts_text: str,
    enough: set[str],
    gaps: set[str],
    taxonomy: SkillTaxonomy,
) -> list[dict[str, Any]]:
    """Drop claims naming what the facts do not, or advising to learn what the user already has.

    The model named real certificates and tools here with a citation that does not mention them.
    Thai text cannot be checked this way, but tool and certificate names are in Latin letters.
    """
    known = facts_text.casefold()
    kept = []
    wrong_step = False
    for claim in claims:
        text = claim["text_th"]
        names = [name.rstrip(".-").casefold() for name in _NAMED_THING.findall(text)]
        if not all(name in known for name in names):
            continue
        named = set(taxonomy.find(text))
        if _ADVICE_TO_LEARN.search(text) and named & enough and not named & gaps:
            wrong_step = True
            continue
        kept.append(claim)
    # "ต่อด้วย…" and "สุดท้าย…" mean nothing once a step is gone; the computed gaps still answer.
    if wrong_step:
        return [claim for claim in kept if not _ADVICE_TO_LEARN.search(claim["text_th"])]
    return kept


def role_evidence(roles: Iterable[RoleProfile]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for role in roles:
        url = next((s["url"] for s in role.sources if s.get("url")), None)
        out[f"role-{role.role_id}"] = {"label_th": f"ข้อมูลตำแหน่ง {role.title_en}", "url": url}
    return out


def claim_lines(claims: Iterable[Mapping[str, Any]], cites: Citations) -> list[str]:
    return [f"- {c['text_th']} {cites.mark(c['evidence_ids'])}".rstrip() for c in claims]


def experience_answer(profile: Mapping[str, Any]) -> Answer:
    section = profile["experience"]
    cites = Citations(profile["evidence"])
    lines = claim_lines(section["summary"], cites)
    if section["total_months"]:
        lines.append(f"รวมประสบการณ์ประมาณ {section['total_months']} เดือน")
    return Answer(text="\n".join(lines) or NO_EXPERIENCE_TH, sources=cites.sources)


def note_evidence(chunks: Iterable[Chunk]) -> dict[str, dict[str, Any]]:
    """Citation data for retrieved chunks: a draft note says it has not been reviewed."""
    out: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        label = f"{chunk.title} ({_DRAFT_NOTE_TH})" if chunk.status == "draft" else chunk.title
        url = next((s for s in chunk.sources if s.startswith("http")), None)
        out[f"rag-{chunk.chunk_id}"] = {"label_th": label, "url": url}
    return out


def note_facts(chunks: Iterable[Chunk]) -> list[dict[str, Any]]:
    return [
        {"text": chunk.text[:_MAX_NOTE_CHARS], "evidence_ids": [f"rag-{chunk.chunk_id}"]}
        for chunk in chunks
    ]


def _note_line(chunk: Chunk, cites: Citations) -> str:
    """The heading and what the trait looks like at work, which the second paragraph says."""
    _title, heading, *body = chunk.text.split("\n", 2)
    paragraphs = [p.strip() for p in "\n".join(body).split("\n\n") if p.strip()]
    text = paragraphs[1] if len(paragraphs) > 1 else paragraphs[0]
    return f"- {heading}: {text} {cites.mark([f'rag-{chunk.chunk_id}'])}"


def work_style_answer(profile: Mapping[str, Any], notes: Sequence[Chunk] = ()) -> Answer:
    section = profile["work_style"]
    cites = Citations(note_evidence(notes))
    parts = [section["summary_th"]]
    if notes:
        lines = "\n".join(_note_line(chunk, cites) for chunk in notes)
        parts.append(f"ความหมายในการทำงาน:\n{lines}")
    parts.append(section["disclaimer_th"])
    return Answer(text="\n\n".join(parts), sources=cites.sources)


WHOLE_WORK_STYLE_TH = "อยากดูทุกด้าน พิมพ์ว่า “สรุปสไตล์การทำงานของฉัน” ได้ครับ"


def work_style_aspect_answer(profile: Mapping[str, Any], trait: str, note: Chunk | None) -> Answer:
    """One aspect of the work style, led by what the user chose for it (Design.md §4.6)."""
    section = profile["work_style"]
    cites = Citations(note_evidence([note] if note else []))
    said = next((t["label_th"] for t in section["traits"] if t["trait"] == trait), None)
    heading = note.text.split("\n")[1] if note else trait
    name = re.sub(r"\s*\([a-z_]+\)$", "", heading)
    lead = f"คุณระบุว่า {said}" if said else "คุณยังไม่ได้ตอบคำถามด้านนี้ในแบบสอบถาม"
    parts = [f"ด้าน{name}: {lead}"]
    if note:
        parts.append(f"ความหมายในการทำงาน:\n{_note_line(note, cites)}")
    parts += [WHOLE_WORK_STYLE_TH, section["disclaimer_th"]]
    return Answer(text="\n\n".join(parts), sources=cites.sources)


def skill_facts(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Names, levels and evidence ids only: no CV text reaches the LLM (FR-12)."""
    return {
        "level_meaning": LEVEL_MEANING_TH,
        "hard_skills": [
            {
                "name": s["name_th"],
                "level": s["level"],
                **({"years": s["years"]} if s.get("years") is not None else {}),
                "evidence_ids": s["evidence_ids"],
            }
            for s in profile["hard_skills"]
        ],
        "soft_skills": [
            {"name": s["name_th"], "evidence_ids": s["evidence_ids"]}
            for s in profile["soft_skills"]
        ],
    }


def skill_fallback(profile: Mapping[str, Any], cites: Citations) -> list[str]:
    lines = [
        f"- {s['name_th']} ระดับ {s['level']} {cites.mark(s['evidence_ids'])}".rstrip()
        for s in profile["hard_skills"]
    ]
    lines.extend(
        f"- {s['name_th']} {cites.mark(s['evidence_ids'])}".rstrip() for s in profile["soft_skills"]
    )
    return lines or [NO_SKILLS_TH]


def _gap_facts(match: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = ("name_th", "kind", "required_level", "user_level")
    return [{key: gap[key] for key in keys if key in gap} for gap in match["gaps"]]


def _role_facts(match: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "title": match["title_th"],
        "match_pct": match["match_pct"],
        "evidence_ids": [f"role-{match['role_id']}"],
        "matched": [
            {"name": s["name_th"], "evidence_ids": s["evidence_ids"]} for s in match["matched"]
        ],
        "gaps": _gap_facts(match),
    }


def blind_spot_facts(profile: Mapping[str, Any], matches: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "saved_blind_spots": [
            {"text_th": c["text_th"], "evidence_ids": c["evidence_ids"]}
            for c in profile["blind_spots"]
        ],
        "top_roles": [_role_facts(m) for m in matches["roles"][:_MAX_ROLES]],
    }


def _gap_names(match: Mapping[str, Any]) -> str:
    return ", ".join(gap["name_th"] for gap in match["gaps"][:_MAX_GAPS_SHOWN])


def blind_spot_fallback(
    profile: Mapping[str, Any], matches: Mapping[str, Any], cites: Citations
) -> list[str]:
    lines = claim_lines(profile["blind_spots"], cites)
    for match in matches["roles"][:_MAX_ROLES]:
        if match["gaps"]:
            mark = cites.mark([f"role-{match['role_id']}"])
            lines.append(f"- สาย {match['title_th']} ยังขาด {_gap_names(match)} {mark}".rstrip())
    return lines or [NO_BLIND_SPOTS_TH]


def matching_facts(matches: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "threshold": matches["threshold"],
        "roles": [_role_facts(m) for m in matches["roles"]],
    }


def matching_answer_lines(
    matches: Mapping[str, Any], reasons: Sequence[str], cites: Citations, *, asked: bool = False
) -> list[str]:
    if asked:
        lines = [ASKED_ROLES_HEADING_TH]
    elif matches["below_threshold"]:
        lines = [f"ยังไม่มีสายงานที่ตรงถึง {matches['threshold']}% สายงานที่ใกล้ที่สุดคือ:"]
    else:
        lines = ["สายงานที่ตรงกับคุณมากที่สุด:"]
    for number, match in enumerate(matches["roles"], start=1):
        mark = cites.mark([f"role-{match['role_id']}"])
        lines.append(f"{number}. {match['title_th']} ตรง {match['match_pct']}% {mark}".rstrip())
    lines.extend(reasons)
    top = matches["roles"][0] if matches["roles"] else None
    if top is not None and top["gaps"]:
        lines.append(f"สิ่งที่ควรเพิ่มสำหรับสาย {top['title_th']}: {_gap_names(top)}")
    lines.append(MATCH_NOTE_TH)
    return lines
