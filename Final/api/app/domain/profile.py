"""Build a profile from the CV, answers and chat facts (Design.md §4.2, PRD FR-15 – FR-17).

Pure Python. Skills, levels, work style, months and preferences are worked out here, each with its
evidence. The LLM only words the experience summary and blind spots, and `parse_claims` checks them.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.cv_parser import project_lines, without_contact
from app.domain.matching.skills import SkillTaxonomy
from app.domain.questionnaire import Questionnaire

DISCLAIMER_TH = "ผลนี้มาจากความชอบที่คุณระบุเอง ไม่ใช่การวินิจฉัยบุคลิกภาพ"  # DesignSystem.md
HIGH_SELF_RATING = 4
# hard: the lowest claim, since the user has it but never gave a level. Soft skills only count as
# present or not in role scoring.
UNRATED_LEVELS = {"hard": 1, "soft": 2}
_MAX_EXCERPT = 200
_MAX_FACT_TEXT = 150
_MAX_HARD_FACTS = 30
_MAX_OTHER_FACTS = 10
_MAX_CLAIMS = 5
_MAX_CLAIM_TEXT = 300
# The model sometimes copies the field into the sentence: (evidence_ids: ["role-x"]).
_ID_LABEL = re.compile(
    r"""[(\[（]?\s*evidence[_ ]?ids?\s*[:=]?\s*"""
    r"""(?:\[[^\]]*\]|["'][^"']*["']|[^\s)\]]+)?\s*[)\]）]?""",
    re.IGNORECASE,
)
# Midpoints of the questionnaire's ranges; the top and bottom ranges use their one stated bound.
_SALARY_THB = {
    "lt_20k": 20_000,
    "20k_30k": 25_000,
    "30k_45k": 37_500,
    "45k_60k": 52_500,
    "gt_60k": 60_000,
}
_MIN_MONTHS = {"1_3y": 12, "gt_3y": 36}  # the least each range can mean


@dataclass(frozen=True, slots=True)
class ChatRow:
    kind: str
    value: dict[str, Any]
    evidence_id: str
    excerpt: str


@dataclass
class ProfileDraft:
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    hard_skills: list[dict[str, Any]] = field(default_factory=list)
    soft_skills: list[dict[str, Any]] = field(default_factory=list)
    work_style: dict[str, Any] = field(default_factory=dict)
    total_months: int = 0
    fallback_experience: list[dict[str, Any]] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    llm_facts: dict[str, Any] = field(default_factory=dict)

    @property
    def skill_ids(self) -> set[str]:
        return {s["skill_id"] for s in [*self.hard_skills, *self.soft_skills]}


def _claim(text: str, evidence_ids: list[str]) -> dict[str, Any]:
    return {"text_th": text, "evidence_ids": evidence_ids, "edited_by_user": False}


def custom_id(name: str) -> str:
    # Free text may hold "/" or Thai, and this id goes in a URL path (Contract §2.5).
    return "custom-" + hashlib.sha256(name.casefold().encode()).hexdigest()[:12]


class _Builder:
    def __init__(
        self,
        *,
        cv_lines: list[str],
        questionnaire: Questionnaire,
        taxonomy: SkillTaxonomy,
        roles: list[dict[str, Any]],
        removed: frozenset[str],
    ) -> None:
        self.removed = removed
        self.cv_lines = cv_lines
        self.questionnaire = questionnaire
        self.taxonomy = taxonomy
        self.roles = roles
        self.evidence: dict[str, dict[str, Any]] = {}
        self.skills: dict[str, dict[str, Any]] = {}

    def _cite(self, evidence_id: str, kind: str, label: str, excerpt: str) -> str:
        self.evidence[evidence_id] = {
            "id": evidence_id,
            "kind": kind,
            "label_th": label,
            "excerpt": excerpt[:_MAX_EXCERPT],
        }
        return evidence_id

    def cite_cv(self, line_no: int | None, text: str) -> str:
        if line_no is not None and 1 <= line_no <= len(self.cv_lines):
            return self._cite(
                f"cv-{line_no}", "cv_line", f"CV บรรทัด {line_no}", self.cv_lines[line_no - 1]
            )
        # Added or changed by the user when confirming: there is no line to point at.
        digest = hashlib.sha256(text.encode()).hexdigest()[:12]
        return self._cite(f"cv-confirmed-{digest}", "cv_line", "CV ที่คุณยืนยัน", text)

    def cite_answer(self, question_id: str, excerpt: str) -> str:
        label = f"แบบสอบถามข้อ {self.questionnaire.number(question_id)}"
        return self._cite(f"answer-{question_id}", "answer", label, excerpt)

    def cite_chat(self, row: ChatRow) -> str:
        return self._cite(row.evidence_id, "chat", "แชท", row.excerpt)

    def option_label(self, question_id: str, value: str) -> str:
        question = self.questionnaire.question(question_id) or {}
        for option in question.get("options", []):
            if option["value"] == value:
                return str(option["label_th"])
        return value

    def add_skill(
        self,
        *,
        name: str,
        skill_id: str | None,
        level: int | None,
        evidence_id: str,
        kind: str = "hard",
        keep_higher: bool = False,
    ) -> None:
        known = self.taxonomy.get(skill_id) if skill_id else None
        if known is None:  # typed by hand: "Kubernetes" must score like the skill it names
            found = self.taxonomy.find(name)
            known = self.taxonomy.get(found[0]) if len(found) == 1 else None
        key = known.id if known else custom_id(name)
        skill = self.skills.get(key)
        if skill is None:
            skill = self.skills[key] = {
                "skill_id": key,
                "name_th": known.name_th if known else name,
                "name_en": known.name_en if known else name,
                "kind": known.type if known else kind,
                "level": None,
                "evidence_ids": [],
                "edited_by_user": False,
            }
        # Sources arrive from weakest to strongest. Within one source, the higher level stands.
        if level is not None and not (keep_higher and (skill["level"] or 0) > level):
            skill["level"] = level
        if evidence_id not in skill["evidence_ids"]:
            skill["evidence_ids"].append(evidence_id)

    def finished_skills(self, kind: str) -> list[dict[str, Any]]:
        default = UNRATED_LEVELS[kind]
        return [
            {**skill, "level": skill["level"] or default}
            for skill in self.skills.values()
            if skill["kind"] == kind and skill["skill_id"] not in self.removed
        ]

    def fact_text(self, text: str | None) -> str | None:
        """Text for the LLM: no contact details, and nothing that names a removed skill (FR-31)."""
        clean = without_contact(text or "")
        if not clean or not self.removed.isdisjoint(self.taxonomy.find(clean)):
            return None
        return clean[:_MAX_FACT_TEXT]


def _add_all_skills(
    b: _Builder, cv: dict[str, Any] | None, answers: dict[str, Any], chat: list[ChatRow]
) -> None:
    # The order matters: a self-rating beats the CV rule, and a later chat answer beats both.
    for skill in (cv or {}).get("skills", []):
        evidence_id = b.cite_cv(skill.get("line_no"), skill["name"])
        b.add_skill(
            name=skill["name"],
            skill_id=skill.get("skill_id"),
            level=skill.get("level"),
            evidence_id=evidence_id,
            keep_higher=True,
        )
    for question in b.questionnaire.questions():
        question_id, value = question["question_id"], answers.get(question["question_id"])
        if value is None:
            continue
        if question.get("slot") == "hard_skills":
            names = {}
            for item in value:
                known = b.taxonomy.get(item["skill_id"])
                names[item["skill_id"]] = known.name_en if known else item["skill_id"]
            # One citation for the whole answer, so it must quote every skill in it.
            evidence_id = b.cite_answer(question_id, ", ".join(map(str, names.values())))
            for item in value:
                name = names[item["skill_id"]]
                b.add_skill(
                    name=name,
                    skill_id=item["skill_id"],
                    level=item["level"],
                    evidence_id=evidence_id,
                )
        elif "skill_id" in question and value >= HIGH_SELF_RATING:
            evidence_id = b.cite_answer(question_id, f"{question['text_th']} ({value}/5)")
            b.add_skill(
                name=question["skill_id"],
                skill_id=question["skill_id"],
                level=value - 1,
                evidence_id=evidence_id,
                kind="soft",
            )
    for row in chat:
        if row.kind == "skill":
            b.add_skill(
                name=row.value["name"],
                skill_id=row.value.get("skill_id"),
                level=row.value.get("level"),
                evidence_id=b.cite_chat(row),
            )
        elif row.kind == "soft_skill":
            found = [i for i in b.taxonomy.find(row.value["name"]) if _is_soft(b, i)]
            b.add_skill(
                name=row.value["name"],
                skill_id=found[0] if found else None,
                level=None,
                evidence_id=b.cite_chat(row),
                kind="soft",
            )


def _is_soft(b: _Builder, skill_id: str) -> bool:
    known = b.taxonomy.get(skill_id)
    return known is not None and known.type == "soft"


def _trait_label(scale: dict[str, Any], answer: int) -> str:
    low, high = scale["min_label_th"], scale["max_label_th"]
    if answer == 3:
        return f"อยู่กึ่งกลางระหว่าง “{low}” กับ “{high}”"
    near = low if answer < 3 else high
    return near if answer in (scale["min"], scale["max"]) else f"ค่อนไปทาง “{near}”"


def trait_label(questionnaire: Questionnaire, trait: str, value: float) -> str:
    """The Thai wording of a work-style value from 0 to 1."""
    question = next(q for q in questionnaire.questions() if q.get("trait") == trait)
    scale = question["scale"]
    return _trait_label(scale, round(value * (scale["max"] - scale["min"])) + scale["min"])


def relabel_trait(
    section: dict[str, Any], trait: str, value: float, questionnaire: Questionnaire
) -> None:
    """Keeps `Profile.work_style` in step when the user edits a preference."""
    label = trait_label(questionnaire, trait, value)
    old = next((t for t in section["traits"] if t["trait"] == trait), None)
    summary = section["summary_th"]
    if old is not None:
        section["summary_th"] = summary.replace(old["label_th"], label)
        old.update(value=round(value, 2), label_th=label)
        return
    section["traits"].append({"trait": trait, "value": round(value, 2), "label_th": label})
    start = "คุณระบุว่า: "
    section["summary_th"] = (
        f"{summary}, {label}" if summary.startswith(start) else f"{start}{label}"
    )


def _work_style(
    b: _Builder, answers: dict[str, Any], chat: list[ChatRow]
) -> tuple[dict[str, Any], dict[str, float]]:
    traits: list[dict[str, Any]] = []
    for question in b.questionnaire.questions():
        answer = answers.get(question["question_id"])
        if question.get("slot") != "work_style" or "trait" not in question or answer is None:
            continue
        scale = question["scale"]
        value = round((answer - scale["min"]) / (scale["max"] - scale["min"]), 2)
        traits.append(
            {"trait": question["trait"], "value": value, "label_th": _trait_label(scale, answer)}
        )
    said = [t["label_th"] for t in traits]
    said += [row.value["text"] for row in chat if row.kind == "preference"]
    summary = f"คุณระบุว่า: {', '.join(said)}" if said else "ยังไม่ได้ระบุรูปแบบการทำงานที่ชอบ"
    section = {"summary_th": summary, "traits": traits, "disclaimer_th": DISCLAIMER_TH}
    return section, {t["trait"]: t["value"] for t in traits}


def _skills_said_with(b: _Builder, row: ChatRow, chat: list[ChatRow]) -> tuple[str, ...]:
    """Skills from the message that told this experience: extraction keeps them apart, and without
    the link the LLM reports the skill as having no experience behind it."""
    names = []
    for other in chat:
        skill_id = other.value.get("skill_id")
        if (
            other.kind == "skill"
            and other.evidence_id == row.evidence_id
            and skill_id not in b.removed
        ):
            known = b.taxonomy.get(skill_id) if skill_id else None
            names.append(known.name_en if known else other.value["name"])
    return tuple(names)


def _experience(
    b: _Builder, cv: dict[str, Any] | None, answers: dict[str, Any], chat: list[ChatRow]
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Total months, fallback claims, and the entries for the LLM."""
    entries: dict[tuple[str, str], dict[str, Any]] = {}

    def add(item: dict[str, Any], evidence_id: str, skills: tuple[str, ...] = ()) -> None:
        key = (item["title"].casefold(), (item.get("company") or "").casefold())
        entry = entries.setdefault(key, {**item, "evidence_ids": [], "skills_used": []})
        entry["months"] = entry.get("months") or item.get("months")
        entry["evidence_ids"].append(evidence_id)
        entry["skills_used"] = list(dict.fromkeys([*entry["skills_used"], *skills]))

    for item in (cv or {}).get("experience", []):
        add(item, b.cite_cv(item.get("line_no"), item["title"]))
    none_row = None
    for row in chat:
        if row.kind != "experience":
            continue
        if row.value.get("none"):
            none_row = row
        else:
            add(row.value, b.cite_chat(row), _skills_said_with(b, row, chat))

    stated = sum(entry.get("months") or 0 for entry in entries.values())
    answer = answers.get("ex_it_experience")
    total = max(stated, _MIN_MONTHS.get(answer, 0))

    claims = [_claim(_entry_text(entry), entry["evidence_ids"]) for entry in entries.values()]
    if not claims and answer is not None:
        label = b.option_label("ex_it_experience", answer)
        evidence_id = b.cite_answer("ex_it_experience", label)
        claims = [_claim(f"ประสบการณ์ด้าน IT ที่คุณระบุ: {label}", [evidence_id])]
    if not claims and none_row is not None:
        claims = [_claim("ยังไม่มีประสบการณ์ทำงานด้าน IT", [b.cite_chat(none_row)])]
    facts = [
        {
            "title": entry["title"],
            "company": entry.get("company"),
            "months": entry.get("months"),
            "summary": b.fact_text(entry.get("summary")),
            "skills_used": entry["skills_used"],
            "evidence_ids": entry["evidence_ids"],
        }
        for entry in entries.values()
    ]
    return total, claims, facts[:_MAX_OTHER_FACTS]


def _projects(b: _Builder) -> list[dict[str, Any]]:
    """Project lines of the CV, as facts only: they have no field of their own in the CV review.

    A line that names a removed skill stays out, so the skill never reaches the LLM (FR-31).
    """
    facts: list[dict[str, Any]] = []
    for line_no, line in project_lines(b.cv_lines):
        if len(facts) == _MAX_OTHER_FACTS:
            break
        text = b.fact_text(line)
        if text:
            facts.append({"text": text, "evidence_ids": [b.cite_cv(line_no, line)]})
    return facts


def _entry_text(entry: dict[str, Any]) -> str:
    text = str(entry["title"])
    if entry.get("company"):
        text += f" ที่ {entry['company']}"
    if entry.get("months"):
        text += f" ({entry['months']} เดือน)"
    return text


def _role_ids(text: str, roles: list[dict[str, Any]]) -> list[str]:
    wanted = text.casefold()
    names = [(r["id"], r["name_en"].casefold(), r["name_th"].casefold()) for r in roles]
    full = [i for i, en, th in names if en in wanted or th in wanted]
    if full:
        return full
    partial = [i for i, en, th in names if wanted in en or wanted in th]
    return partial if len(partial) == 1 else []  # "engineer" alone names no role


def _preferences(
    b: _Builder, answers: dict[str, Any], chat: list[ChatRow], work_style: dict[str, float]
) -> dict[str, Any]:
    roles: list[str] = list(answers.get("go_interested_roles") or [])
    locations: list[str] = []
    if "go_location" in answers:
        locations.append(b.option_label("go_location", answers["go_location"]))
    salary = _SALARY_THB.get(answers.get("go_salary", ""))
    for row in chat:
        if row.kind != "goal":
            continue
        for text in row.value.get("roles", []):
            roles.extend(_role_ids(text, b.roles))
        locations.extend(row.value.get("locations", []))
        salary = row.value.get("desired_salary_thb") or salary
    preferences: dict[str, Any] = {
        "interested_roles": list(dict.fromkeys(roles)),
        "locations": list(dict.fromkeys(locations)),
        "work_style": work_style,
    }
    if salary:
        preferences["desired_salary_thb"] = salary
    return preferences


def _education_facts(
    b: _Builder, cv: dict[str, Any] | None, answers: dict[str, Any], chat: list[ChatRow]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for item in (cv or {}).get("education", []):
        evidence_id = b.cite_cv(item.get("line_no"), item.get("school") or "")
        facts.append(
            {
                "institution": without_contact(item.get("school") or "") or None,
                "degree": item.get("degree"),
                "field": item.get("field"),
                "evidence_ids": [evidence_id],
            }
        )
    if "ed_level" in answers:
        label = b.option_label("ed_level", answers["ed_level"])
        facts.append({"degree": label, "evidence_ids": [b.cite_answer("ed_level", label)]})
    for row in chat:
        if row.kind == "education":
            facts.append({**row.value, "evidence_ids": [b.cite_chat(row)]})
    return facts[:_MAX_OTHER_FACTS]


def _examples(b: _Builder, answers: dict[str, Any], chat: list[ChatRow]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    text = b.fact_text(answers.get("ss_example"))
    if text:
        evidence_id = b.cite_answer("ss_example", answers["ss_example"])
        examples.append({"text": text, "evidence_ids": [evidence_id]})
    for row in chat:
        text = b.fact_text(row.value.get("example")) if row.kind == "soft_skill" else None
        if text:
            examples.append({"text": text, "evidence_ids": [b.cite_chat(row)]})
    return examples[:_MAX_OTHER_FACTS]


def _skill_facts(skills: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [
        {"name": s["name_en"], "level": s["level"], "evidence_ids": s["evidence_ids"]}
        for s in skills[:limit]
    ]


def build_draft(
    *,
    cv: dict[str, Any] | None,
    cv_lines: list[str],
    answers: dict[str, Any],
    chat: list[ChatRow],
    questionnaire: Questionnaire,
    taxonomy: SkillTaxonomy,
    roles: list[dict[str, Any]],
    removed: frozenset[str] = frozenset(),
) -> ProfileDraft:
    """`cv` is the parsed data of a confirmed CV only (FR-3); `chat` runs oldest first.

    `removed` skills stay out, wherever they come from, and so never reach the LLM (FR-31).
    """
    b = _Builder(
        cv_lines=cv_lines,
        questionnaire=questionnaire,
        taxonomy=taxonomy,
        roles=roles,
        removed=removed,
    )
    answers = questionnaire.known_answers(answers)
    _add_all_skills(b, cv, answers, chat)
    work_style, traits = _work_style(b, answers, chat)
    total_months, fallback, experience_facts = _experience(b, cv, answers, chat)
    hard, soft = b.finished_skills("hard"), b.finished_skills("soft")
    llm_facts = {
        "hard_skills": _skill_facts(hard, _MAX_HARD_FACTS),
        "soft_skills": _skill_facts(soft, _MAX_OTHER_FACTS),
        "experience": experience_facts,
        "projects": _projects(b),
        "experience_fallback": [
            {"text": c["text_th"], "evidence_ids": c["evidence_ids"]} for c in fallback
        ],
        "total_months": total_months,
        "education": _education_facts(b, cv, answers, chat),
        "examples": _examples(b, answers, chat),
    }
    return ProfileDraft(
        evidence=b.evidence,
        hard_skills=hard,
        soft_skills=soft,
        work_style=work_style,
        total_months=total_months,
        fallback_experience=fallback,
        preferences=_preferences(b, answers, chat, traits),
        llm_facts=llm_facts,
    )


def _without_ids(text: str, evidence: set[str]) -> str | None:
    """The sentence without a copied id field, or None if it still shows an id to the user."""
    cleaned = re.sub(r"\s{2,}", " ", _ID_LABEL.sub(" ", text)).strip()
    if "evidence" in cleaned.casefold():
        return None
    for evidence_id in evidence:
        if re.search(rf"(?<![\w-]){re.escape(evidence_id)}(?![\w-])", cleaned):
            return None
    return cleaned


def parse_claims(
    items: Any,
    *,
    evidence: set[str],
    facts_text: str,
    taxonomy: SkillTaxonomy,
    own_skills: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep the LLM's claims that hold up (FR-16).

    A claim needs real text and at least one real evidence id, and may only use numbers that are in
    the facts. With `own_skills`, it may only name skills the user has or that the facts mention,
    such as in a job title. A blind spot leaves that out, because it may name what is missing.
    A copied id field is cut from the sentence, and a sentence that still shows an id is dropped.
    """
    if not isinstance(items, list):
        return []
    known_numbers = set(re.findall(r"\d+", facts_text))
    allowed_skills = None if own_skills is None else own_skills | set(taxonomy.find(facts_text))
    claims: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text, ids = item.get("text_th"), item.get("evidence_ids")
        if not isinstance(text, str) or not text.strip() or not isinstance(ids, list):
            continue
        real = [i for i in dict.fromkeys(x for x in ids if isinstance(x, str)) if i in evidence]
        text = _without_ids(text, evidence)
        if not text:
            continue
        if not real or not set(re.findall(r"\d+", text)) <= known_numbers:
            continue
        if allowed_skills is not None and not set(taxonomy.find(text)) <= allowed_skills:
            continue
        claims.append(_claim(text.strip()[:_MAX_CLAIM_TEXT], real))
    return claims[:_MAX_CLAIMS]


def facts_as_text(facts: dict[str, Any]) -> str:
    return json.dumps(facts, ensure_ascii=False)
