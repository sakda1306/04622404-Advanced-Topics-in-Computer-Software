"""Rules-only CV parsing (PRD FR-2, Design.md §4.1): taxonomy matching, sections, entries."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.cv_parser import parse_cv, project_lines
from app.domain.matching.skills import SkillTaxonomy, load_taxonomy
from app.infra.pdf_text import clean_line, extract_lines
from tests.pdf_fixtures import make_pdf

DATA_DIR = Path(__file__).parents[2] / "data"
TODAY = date(2026, 11, 3)


@pytest.fixture(scope="module")
def taxonomy() -> SkillTaxonomy:
    return load_taxonomy(str(DATA_DIR))


# --- skill matching ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Python, Docker and Kubernetes", ["python", "docker", "kubernetes"]),
        ("Built REST APIs with Node.js", ["rest-api", "nodejs"]),
        ("C++ and C# developer", ["cpp", "csharp"]),
        ("Deployed on Amazon Web Services", ["aws"]),
        ("Used Redis for caching", ["caching", "nosql"]),
    ],
)
def test_taxonomy_finds_skills(taxonomy: SkillTaxonomy, line: str, expected: list[str]) -> None:
    assert set(expected) <= set(taxonomy.find(line))


@pytest.mark.parametrize(
    "line",
    [
        "I can go to the office",  # no "go" skill from plain English
        "Research and development",  # not the R language
        "Handled user ids in the log",  # not IDS
        "Javascripting is fun",  # no partial word match
    ],
)
def test_taxonomy_ignores_plain_words(taxonomy: SkillTaxonomy, line: str) -> None:
    found = taxonomy.find(line)
    assert "r" not in found
    assert "siem" not in found
    assert "javascript" not in found


def test_taxonomy_matches_thai_names(taxonomy: SkillTaxonomy) -> None:
    skill = taxonomy.get("caching")
    assert skill is not None
    thai_main = skill.name_th.split("(")[0].strip()
    assert "caching" in taxonomy.find(f"มีประสบการณ์{thai_main}ในระบบจริง")


# --- whole CV ----------------------------------------------------------------------------

CV_EN = [
    "Somchai Jaidee",  # 1
    "somchai@example.com",  # 2
    "Skills",  # 3
    "Python (4 years), Docker, SQL",  # 4
    "Work Experience",  # 5
    "Backend Developer at Acme Co., Ltd.  Jan 2022 - Present",  # 6
    "Built REST APIs with FastAPI and PostgreSQL",  # 7
    "Junior Developer | Beta Soft  06/2020 - 12/2021",  # 8
    "Maintained internal tools",  # 9
    "Education",  # 10
    "Bachelor of Engineering in Computer Engineering",  # 11
    "Kasetsart University 2016 - 2020",  # 12
]


def test_parse_finds_skills_with_lines_and_levels(taxonomy: SkillTaxonomy) -> None:
    parsed = parse_cv(CV_EN, taxonomy, today=TODAY)
    by_id = {s.skill_id: s for s in parsed.skills}
    assert {"python", "docker", "sql", "rest-api"} <= set(by_id)
    assert by_id["python"].line_no == 4
    assert by_id["python"].level == 3  # 4 years
    assert by_id["docker"].level is None  # no years: the user picks a level in the confirm step
    assert by_id["python"].name == "Python"
    assert len(parsed.skills) == len(by_id)  # each skill once


def test_parse_experience_entries(taxonomy: SkillTaxonomy) -> None:
    parsed = parse_cv(CV_EN, taxonomy, today=TODAY)
    first, second = parsed.experience
    assert (first.title, first.company) == ("Backend Developer", "Acme Co., Ltd.")
    assert (first.start, first.end, first.line_no) == ("2022-01", None, 6)
    assert first.months == 59  # Jan 2022 to Nov 2026, both months counted
    assert first.summary == "Built REST APIs with FastAPI and PostgreSQL"
    assert (second.title, second.company) == ("Junior Developer", "Beta Soft")
    assert (second.start, second.end, second.months) == ("2020-06", "2021-12", 19)


def test_parse_education(taxonomy: SkillTaxonomy) -> None:
    (entry,) = parse_cv(CV_EN, taxonomy, today=TODAY).education
    assert entry.school == "Kasetsart University"
    assert entry.degree == "Bachelor of Engineering"
    assert entry.field == "Computer Engineering"
    assert (entry.start, entry.end) == ("2016", "2020")
    assert entry.line_no == 11


def test_parse_clean_cv_has_only_level_warning(taxonomy: SkillTaxonomy) -> None:
    parsed = parse_cv(CV_EN, taxonomy, today=TODAY)
    assert parsed.warnings_th == ["ทักษะบางรายการยังไม่มีระดับ กรุณาเลือกระดับในขั้นตอนยืนยัน"]


CV_TH = [
    "ประวัติการศึกษา",  # 1
    "ปริญญาตรี วิศวกรรมศาสตร์ สาขาวิศวกรรมคอมพิวเตอร์",  # 2
    "มหาวิทยาลัยเกษตรศาสตร์ 2559 - 2563",  # 3
    "ประสบการณ์ทำงาน",  # 4
    "นักพัฒนาซอฟต์แวร์ บริษัท เอ จำกัด มกราคม 2565 - ปัจจุบัน",  # 5
    "ทักษะ",  # 6
    "Python 2 ปี, Git",  # 7
]


def test_parse_thai_cv_with_buddhist_years(taxonomy: SkillTaxonomy) -> None:
    parsed = parse_cv(CV_TH, taxonomy, today=TODAY)
    (edu,) = parsed.education
    assert edu.school == "มหาวิทยาลัยเกษตรศาสตร์"
    assert edu.degree == "ปริญญาตรี"
    assert edu.field == "วิศวกรรมคอมพิวเตอร์"
    assert (edu.start, edu.end) == ("2016", "2020")
    (job,) = parsed.experience
    assert job.start == "2022-01"
    assert job.end is None
    assert job.line_no == 5
    python = next(s for s in parsed.skills if s.skill_id == "python")
    assert python.level == 2


def test_parse_warns_when_things_are_missing(taxonomy: SkillTaxonomy) -> None:
    parsed = parse_cv(
        ["Experience", "Barista at Coffee Shop", "Hobbies", "Reading"], taxonomy, today=TODAY
    )
    assert parsed.skills == []
    assert [e.title for e in parsed.experience] == ["Barista"]
    assert "ไม่พบทักษะที่ระบบรู้จักใน CV กรุณาเพิ่มเองในขั้นตอนยืนยัน" in parsed.warnings_th
    assert "ไม่พบวันที่ของประสบการณ์บางรายการ" in parsed.warnings_th
    assert "ไม่พบข้อมูลการศึกษาใน CV" in parsed.warnings_th


# --- PDF text ----------------------------------------------------------------------------


def test_extract_lines_from_pdf() -> None:
    lines = extract_lines(make_pdf(CV_EN), max_pages=20)
    assert lines[3] == "Python (4 years), Docker, SQL"
    assert len(lines) == len(CV_EN)


@pytest.mark.parametrize(
    "data",
    [make_pdf(None), b"%PDF-1.4\nnot really a pdf", make_pdf(["a"])],
    ids=["scanned", "broken", "almost-empty"],
)
def test_unreadable_pdf(data: bytes) -> None:
    with pytest.raises(AppError) as caught:
        extract_lines(data, max_pages=20)
    assert caught.value.code == ErrorCode.CV_UNREADABLE


def test_too_many_pages_is_unreadable() -> None:
    with pytest.raises(AppError) as caught:
        extract_lines(make_pdf(CV_EN, pages=3), max_pages=2)
    assert caught.value.code == ErrorCode.CV_UNREADABLE


# --- text from real Thai PDFs (found with a real Thai CV on 1 Nov) ------------------------


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        # Some fonts map Thai marks to NUL; Postgres JSONB refuses NUL, so it must go.
        ("ชื\x00อเล่น", "ชือเล่น"),
        ("tab\there\x07bell\u200b", "tab here bell"),
        # NIKHAHIT + SARA AA written for SARA AM.
        ("ทํางาน", "ทำงาน"),
        # Spaces around the dots of Thai abbreviations.
        ("เม . ย . 2569 – ป\x00จจุบัน", "เม.ย. 2569 – ปจจุบัน"),
        ("ปวช . ( เทคโนโลยี )", "ปวช. ( เทคโนโลยี )"),
    ],
)
def test_clean_line(raw: str, clean: str) -> None:
    assert clean_line(raw) == clean


def test_extract_lines_drops_nul() -> None:
    lines = extract_lines(make_pdf(["Python\x00 developer with Docker and SQL"]), max_pages=20)
    assert lines == ["Python developer with Docker and SQL"]


def test_thai_present_without_its_mark(taxonomy: SkillTaxonomy) -> None:
    lines = ["ประสบการณ์ทำงาน", "นักพัฒนา Full Stack เม.ย. 2569 – ปจจุบัน"]
    (job,) = parse_cv(lines, taxonomy, today=TODAY).experience
    assert (job.title, job.start, job.end) == ("นักพัฒนา Full Stack", "2026-04", None)


# Two-column CVs (common in designed templates): all headings come out first, content later.
TWO_COLUMN = [
    "การศึกษา",
    "ประสบการณ์ทำงาน",
    "ทักษะ ทักษะซอฟต์แวร์",
    "โปรเจกต์",
    "ปวช. ( เทคโนโลยีสารสนเทศ )",
    "วิทยาลัยเทคนิคตัวอย่าง",
    "ปริญญาตรี ( วิศวกรรมคอมพิวเตอร์ )",
    "มหาวิทยาลัยตัวอย่าง ( กำลังศึกษา )",
    "ร่วมมือกับนักศึกษาจากมหาวิทยาลัยต่างประเทศ ออกแบบและพัฒนาเทคโนโลยีเชิงนวัตกรรมร่วมกัน",
    "Python, Java",
]


def test_short_line_starting_with_a_thai_heading_is_a_heading(taxonomy: SkillTaxonomy) -> None:
    assert parse_cv(TWO_COLUMN, taxonomy, today=TODAY).experience == []


def test_education_found_outside_its_section(taxonomy: SkillTaxonomy) -> None:
    first, second = parse_cv(TWO_COLUMN, taxonomy, today=TODAY).education
    assert (first.school, first.degree, first.field) == (
        "วิทยาลัยเทคนิคตัวอย่าง",
        "ปวช.",
        "เทคโนโลยีสารสนเทศ",
    )
    assert (second.school, second.degree, second.field) == (
        "มหาวิทยาลัยตัวอย่าง",
        "ปริญญาตรี",
        "วิศวกรรมคอมพิวเตอร์",
    )


def test_warns_when_no_experience_was_found(taxonomy: SkillTaxonomy) -> None:
    warnings = parse_cv(TWO_COLUMN, taxonomy, today=TODAY).warnings_th
    assert "ไม่พบประสบการณ์ทำงานใน CV ถ้ามี กรุณาเพิ่มเองในขั้นตอนยืนยัน" in warnings


def test_project_lines_stop_at_the_next_heading() -> None:
    lines = ["Name", "Projects", "Tracker app", "", "Education", "BSc", "โปรเจกต์", "แอปจดบันทึก"]
    assert project_lines(lines) == [(3, "Tracker app"), (8, "แอปจดบันทึก")]


def test_no_projects_heading_gives_no_lines() -> None:
    assert project_lines(["Name", "Skills", "Python"]) == []


def test_projects_add_no_experience_entry(taxonomy: SkillTaxonomy) -> None:
    lines = ["Projects", "Tracker app, Jun 2025 - Oct 2025"]
    assert parse_cv(lines, taxonomy, today=date(2026, 11, 4)).experience == []


# --- found by testing the running system


def _parsed(*lines: str) -> Any:
    return parse_cv(list(lines), load_taxonomy(str(DATA_DIR)), today=TODAY)


def test_a_thai_project_line_inside_experience_is_not_a_heading() -> None:
    parsed = _parsed(
        "ประสบการณ์ทำงาน",
        "นักพัฒนา บริษัท เอ มกราคม 2565 - มีนาคม 2565",
        "โครงการ ระบบบัญชี",
        "นักวิเคราะห์ บริษัท บี มกราคม 2566 - มีนาคม 2566",
    )
    assert [e.title for e in parsed.experience] == ["นักพัฒนา", "นักวิเคราะห์"]


def test_a_project_heading_alone_still_starts_the_section() -> None:
    assert project_lines(["โครงการ", "ระบบบัญชี"]) == [(2, "ระบบบัญชี")]


@pytest.mark.parametrize("dates", ["ม.ค. 65 - มี.ค. 65", "2022-01 - 2022-03"])
def test_more_date_forms_are_read(dates: str) -> None:
    parsed = _parsed("Experience", f"Developer at Acme {dates}")
    assert parsed.experience[0].months == 3
    assert parsed.experience[0].start == "2022-01"


def test_an_email_or_link_is_not_read_as_a_skill() -> None:
    parsed = _parsed(
        "python.lover@example.com", "https://github.com/react-kubernetes", "Skills", "SQL"
    )
    assert [s.skill_id for s in parsed.skills] == ["sql"]


def test_an_email_is_not_read_as_a_school() -> None:
    assert _parsed("pat@example-university.ac.th", "Skills", "SQL").education == []


def test_contact_lines_stay_out_of_the_summary() -> None:
    parsed = _parsed(
        "Experience",
        "Developer at Acme Jan 2022 - Mar 2022",
        "ทำระบบบัญชี",
        "pat@example.com 081-234-5678",
    )
    assert parsed.experience[0].summary == "ทำระบบบัญชี"
