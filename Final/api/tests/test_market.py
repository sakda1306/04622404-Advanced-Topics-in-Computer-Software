"""JobThai provider and the shared job cache (PRD FR-22a – FR-22f, Design.md §7)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container
from app.domain import market
from app.domain.market import Salary
from app.domain.matching.roles import RoleProfile, load_catalogue
from app.domain.matching.skills import load_taxonomy
from app.infra.models import JobPosting, RefreshLog, RoleCache
from app.providers.apify_jobthai import ApifyJobThaiProvider
from app.providers.base import Posting, ProviderError
from app.services import market_service

DATA_DIR = "../data"
CATALOGUE = load_catalogue(DATA_DIR)
TAXONOMY = load_taxonomy(DATA_DIR)
SEARCHES = market.load_role_search(DATA_DIR)
ROLE = next(role for role in CATALOGUE if role.role_id == "data-analyst")


def _item(**overrides: Any) -> dict[str, Any]:
    item = {
        "title": "Data Analyst",
        "company": "บริษัท ตัวอย่าง จำกัด",
        "location": "เขตจตุจักร กรุงเทพมหานคร",
        "province": "กรุงเทพมหานคร",
        "salary": "30,000 - 40,000 บาท",
        "updatedAtText": "31 ต.ค. 69",
        "url": "https://www.jobthai.com/th/job/1",
        "description": "ใช้ SQL และ Python",
        "qualifications": "ติดต่อ hr@example.com",
    }
    return item | overrides


def _posting(**overrides: Any) -> Posting:
    values = {
        "source": "jobthai",
        "title": "Data Analyst",
        "company": "บริษัท ตัวอย่าง จำกัด",
        "location": "เขตจตุจักร กรุงเทพมหานคร",
        "province": "กรุงเทพมหานคร",
        "salary_text": "30,000 - 40,000 บาท",
        "posted_text": "31 ต.ค. 69",
        "url": "https://www.jobthai.com/th/job/1",
        "text": "ใช้ SQL และ Python",
    }
    return Posting(**(values | overrides))


def _provider(handler: Any) -> ApifyJobThaiProvider:
    return ApifyJobThaiProvider("secret-token", transport=httpx.MockTransport(handler))


class FakeProvider:
    name = "fake"

    def __init__(self, result: list[Posting] | Exception) -> None:
        self.result = result
        self.calls = 0

    async def fetch_postings(self, keyword: str, limit: int) -> list[Posting]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def _refresh(
    db: AsyncSession, provider: FakeProvider, role: RoleProfile = ROLE
) -> market_service.RefreshResult:
    return await market_service.refresh_role(
        db, provider, role, searches=SEARCHES, taxonomy=TAXONOMY
    )


# --- the data file


def test_every_role_has_search_terms() -> None:
    assert set(SEARCHES) == {role.role_id for role in CATALOGUE}
    assert all(search.keyword and search.title_terms for search in SEARCHES.values())
    assert all(term == term.lower() for search in SEARCHES.values() for term in search.title_terms)


# --- salary text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("20,000 - 30,000 บาท", Salary(20000, 30000, "month")),
        ("30,000–40,000 บาท (พิจารณาตามประสบการณ์และความสามารถ)", Salary(30000, 40000, "month")),
        ("25,000 บาท", Salary(25000, 25000, "month")),
        ("15K-20K", Salary(15000, 20000, "month")),
        ("25,000 บาท (ประสบการณ์ 3 ปี)", Salary(25000, 25000, "month")),
        ("600,000 - 720,000 บาท/ปี", Salary(600000, 720000, "year")),
        (
            "Monthly THB 40,000–60,000 (based on ability) + incentive of 20–30% of salary; "
            "review after 119 days",
            Salary(40000, 60000, "month"),
        ),
    ],
)
def test_parse_salary(text: str, expected: Salary) -> None:
    assert market.parse_salary(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ตามตกลง",
        "ตามโครงสร้างบริษัทฯ",
        "3 ปี",
        "40,000 - 20,000 บาท",
        "1 2 3",
        "9,000,000 บาท",
        "400 บาท (รายวัน)",
    ],
)
def test_parse_salary_keeps_other_text_out_of_the_ranges(text: str) -> None:
    assert market.parse_salary(text) is None


def test_parse_posted_at_reads_buddhist_years() -> None:
    assert market.parse_posted_at("31 ต.ค. 69") == date(2026, 10, 31)
    assert market.parse_posted_at("1 ม.ค. 2569") == date(2026, 1, 1)
    assert market.parse_posted_at("เมื่อวาน") is None
    assert market.parse_posted_at("31 ก.พ. 69") is None


def test_advertised_range_uses_medians_and_monthly_figures_only() -> None:
    result = market.advertised_range(
        [
            Salary(20000, 30000, "month"),
            Salary(25000, 35000, "month"),
            Salary(200000, 300000, "month"),
            Salary(600000, 900000, "year"),
        ],
        date(2026, 11, 3),
    )
    assert result is not None
    assert (result["min_thb"], result["max_thb"], result["sample_size"]) == (25000, 35000, 3)
    assert result["measure"] == "monthly_base"
    assert result["source_type"] == "advertised"
    assert result["as_of"] == "2026-11-03"
    assert market.advertised_range([Salary(600000, 900000, "year")], date(2026, 11, 3)) is None


# --- ingest filters


@pytest.mark.parametrize(
    ("province", "location", "expected"),
    [
        ("กรุงเทพมหานคร", "MRT พระราม 9", True),
        ("", "เขตจตุจักร กรุงเทพมหานคร", True),
        ("นนทบุรี", "ใกล้กรุงเทพ", False),
        ("ชลบุรี", "อ.บ้านบึง จ.ชลบุรี", False),
        ("", "", False),
    ],
)
def test_is_bangkok(province: str, location: str, expected: bool) -> None:
    assert market.is_bangkok(_posting(province=province, location=location)) is expected


def test_fits_role_by_title_with_word_boundaries() -> None:
    role = next(r for r in CATALOGUE if r.role_id == "qa-engineer")
    assert market.fits_role(_posting(title="QA Engineer", text=""), role, SEARCHES, TAXONOMY)
    assert not market.fits_role(_posting(title="Aquarium Staff", text=""), role, SEARCHES, TAXONOMY)


def _required_skill_names(role: RoleProfile) -> list[str]:
    skills = (TAXONOMY.get(need.skills[0]) for need in role.required)
    return [skill.name_en for skill in skills if skill]


def test_fits_role_by_required_skills_when_the_title_names_no_role() -> None:
    names = _required_skill_names(ROLE)
    many = _posting(title="Officer", text=", ".join(names))
    assert market.fits_role(many, ROLE, SEARCHES, TAXONOMY)
    assert not market.fits_role(_posting(title="Officer", text=names[0]), ROLE, SEARCHES, TAXONOMY)


def test_a_title_naming_another_role_does_not_fit_even_with_the_skills() -> None:
    text = ", ".join(_required_skill_names(ROLE))
    other = _posting(title="Data Scientist", text=text)
    assert not market.fits_role(other, ROLE, SEARCHES, TAXONOMY)
    both = _posting(title="Data Engineer and Data Analyst", text="")
    assert market.fits_role(both, ROLE, SEARCHES, TAXONOMY)


def test_a_generic_programmer_title_can_fit_a_specific_role_by_skills() -> None:
    role = next(r for r in CATALOGUE if r.role_id == "frontend-developer")
    text = ", ".join(_required_skill_names(role))
    assert market.fits_role(_posting(title="Programmer", text=text), role, SEARCHES, TAXONOMY)


def test_a_specific_title_does_not_fit_another_specific_role() -> None:
    role = next(r for r in CATALOGUE if r.role_id == "frontend-developer")
    text = ", ".join(_required_skill_names(role))
    title = _posting(title="SOFTWARE ENGINEER", text=text)
    assert not market.fits_role(title, role, SEARCHES, TAXONOMY)


@pytest.mark.parametrize("title", ["Business Analytics Manager", "Engineering Team Lead"])
def test_skills_alone_do_not_make_a_manager_or_a_lead_fit(title: str) -> None:
    text = ", ".join(_required_skill_names(ROLE))
    assert not market.fits_role(_posting(title=title, text=text), ROLE, SEARCHES, TAXONOMY)


def test_a_manager_or_a_senior_with_the_role_in_the_title_stays() -> None:
    for title in ("Data Analyst Manager", "Senior Data Analyst"):
        assert market.fits_role(_posting(title=title, text=""), ROLE, SEARCHES, TAXONOMY)


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("Senior Data Analyst", "senior"),
        ("Sr. Data Engineer", "senior"),
        ("Junior Programmer", "junior"),
        ("Jr Developer", "junior"),
        ("Data Analyst Intern", "intern"),
        ("นักศึกษาฝึกงาน IT", "intern"),
        ("Tech Lead", "lead"),
        ("Business Analytics Manager", "manager"),
        ("Senior Manager", "manager"),
        ("ผู้จัดการฝ่ายไอที", "manager"),
        ("IT Project Manager", None),
        ("ผู้จัดการโครงการ", None),
        ("Senior Project Manager", "senior"),
        ("Data Analyst", None),
        ("Internal Auditor", None),
        ("Leader Support", None),
    ],
)
def test_job_level_reads_the_title(title: str, level: str | None) -> None:
    assert market.job_level(title) == level


def test_demand_counts_postings_and_leaves_out_soft_skills() -> None:
    postings = [
        _posting(text="Python, SQL และ communication"),
        _posting(title="Analyst", text="Python"),
    ]
    result = market.demand(postings, TAXONOMY)
    assert result["posting_count"] == 2
    top = result["trending_skills"][0]
    assert (top["skill_id"], top["count"]) == ("python", 2)
    assert top["name_th"]
    assert "communication" not in {s["skill_id"] for s in result["trending_skills"]}


# --- the provider


async def test_provider_asks_for_bangkok_it_jobs_without_contacts() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=[_item()])

    postings = await _provider(handler).fetch_postings("Data Analyst", 20)
    assert seen["auth"] == "Bearer secret-token"
    assert "mai_amm~jobthai-scraper" in seen["url"]
    assert "secret-token" not in seen["url"]
    body = seen["body"]
    assert body["keyword"] == "Data Analyst"
    assert body["province"] == "bangkok"
    assert body["jobTypes"] == ["7"]
    assert body["maxItems"] == 20
    assert body["includeContacts"] is False
    assert postings[0].title == "Data Analyst"


async def test_provider_drops_contact_fields_and_items_without_a_title() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        contact = {"email": "hr@example.com", "phone": "0812345678", "howToApply": "โทร 081"}
        return httpx.Response(200, json=[_item(**contact), _item(title=""), "not a job"])

    postings = await _provider(handler).fetch_postings("x", 20)
    assert len(postings) == 1
    assert not hasattr(postings[0], "email")
    assert not hasattr(postings[0], "phone")
    assert "0812345678" not in repr(postings[0])


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(402, text="secret-token over budget"), "http_402"),
        (httpx.Response(200, text="<html>"), "bad_response"),
        (httpx.Response(200, json={"error": "x"}), "bad_response"),
    ],
)
async def test_provider_errors_are_short_codes(response: httpx.Response, code: str) -> None:
    with pytest.raises(ProviderError) as caught:
        await _provider(lambda _request: response).fetch_postings("x", 20)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("error", "code"),
    [(httpx.ReadTimeout("slow"), "timeout"), (httpx.ConnectError("down"), "network")],
)
async def test_provider_network_failures(error: Exception, code: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(ProviderError) as caught:
        await _provider(handler).fetch_postings("x", 20)
    assert caught.value.code == code


async def test_provider_without_a_token_makes_no_call() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called")

    provider = ApifyJobThaiProvider("", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await provider.fetch_postings("x", 20)
    assert caught.value.code == "no_token"


# --- the cache


async def test_refresh_keeps_only_bangkok_postings_that_fit_the_role(
    container: Container,
) -> None:
    provider = FakeProvider(
        [
            _posting(),
            _posting(url="https://www.jobthai.com/th/job/1"),  # the same job again
            _posting(url="https://www.jobthai.com/th/job/2", province="ชลบุรี"),
            _posting(url="https://www.jobthai.com/th/job/3", title="พนักงานขาย", text=""),
            _posting(url="https://www.jobthai.com/th/job/4", salary_text="ตามตกลง"),
        ]
    )
    async with container.sessions() as db:
        result = await _refresh(db, provider)
        rows = (await db.scalars(select(JobPosting))).all()
        cache = await db.get(RoleCache, ROLE.role_id)
        logs = (await db.scalars(select(RefreshLog))).all()

    assert (result.ok, result.fetched, result.kept) == (True, 5, 2)
    assert (result.not_bangkok, result.not_the_role) == (1, 1)
    assert result.levels == {"unstated": 2}
    assert {row.url[-1] for row in rows} == {"1", "4"}
    parsed = next(row for row in rows if row.url.endswith("1"))
    assert (parsed.salary_min, parsed.salary_max, parsed.salary_period) == (30000, 40000, "month")
    assert parsed.posted_at == date(2026, 10, 31)
    unparsed = next(row for row in rows if row.url.endswith("4"))
    assert unparsed.salary_text == "ตามตกลง"
    assert unparsed.salary_min is None
    assert cache is not None
    assert cache.fetched_at is not None
    assert cache.refreshing is False
    assert cache.last_error is None
    assert cache.demand["posting_count"] == 2
    assert cache.salary_advertised["sample_size"] == 1
    assert [(log.role_id, log.status) for log in logs] == [(ROLE.role_id, "ok")]


async def test_refresh_replaces_the_role_and_leaves_other_roles_alone(
    container: Container,
) -> None:
    other = next(role for role in CATALOGUE if role.role_id == "data-engineer")
    async with container.sessions() as db:
        await _refresh(db, FakeProvider([_posting()]))
        await _refresh(db, FakeProvider([_posting(title="Data Engineer")]), other)
        await _refresh(db, FakeProvider([_posting(url="https://www.jobthai.com/th/job/9")]))
        rows = (await db.scalars(select(JobPosting))).all()
    by_role = {row.role_id: row.url[-1] for row in rows}
    assert len(rows) == 2
    assert by_role == {ROLE.role_id: "9", other.role_id: "1"}


@pytest.mark.parametrize(
    ("result", "code"), [(ProviderError("http_402"), "http_402"), ([], "no_results")]
)
async def test_failed_refresh_keeps_the_previous_data(
    container: Container, result: Any, code: str
) -> None:
    async with container.sessions() as db:
        await _refresh(db, FakeProvider([_posting()]))
        first = await db.get(RoleCache, ROLE.role_id)
        assert first is not None
        fetched_at = first.fetched_at
        outcome = await _refresh(db, FakeProvider(result))
        cache = await db.get(RoleCache, ROLE.role_id, populate_existing=True)
        count = await db.scalar(select(func.count()).select_from(JobPosting))
        statuses = sorted((await db.scalars(select(RefreshLog.status))).all())

    assert (outcome.ok, outcome.error) == (False, code)
    assert count == 1
    assert cache is not None
    assert cache.fetched_at == fetched_at
    assert cache.demand["posting_count"] == 1
    assert cache.refreshing is False
    assert cache.last_error == code
    assert statuses == ["failed", "ok"]


async def test_refresh_shows_refreshing_during_the_fetch(container: Container) -> None:
    seen: list[bool] = []

    class Watching(FakeProvider):
        async def fetch_postings(self, keyword: str, limit: int) -> list[Posting]:
            async with container.sessions() as other:
                row = await other.get(RoleCache, ROLE.role_id)
                assert row is not None
                seen.append(row.refreshing)
            return [_posting()]

    async with container.sessions() as db:
        await _refresh(db, Watching([]))
    assert seen == [True]


async def test_an_unexpected_error_does_not_leave_refreshing_on(container: Container) -> None:
    async with container.sessions() as db:
        with pytest.raises(RuntimeError):
            await _refresh(db, FakeProvider(RuntimeError("bug")))
        cache = await db.get(RoleCache, ROLE.role_id, populate_existing=True)
    assert cache is not None
    assert cache.refreshing is False
    assert cache.last_error == "unexpected"


async def test_is_fresh(container: Container) -> None:
    async with container.sessions() as db:
        await _refresh(db, FakeProvider([_posting()]))
        cache = await db.get(RoleCache, ROLE.role_id)
        assert cache is not None
        settings = container.settings
        fetched_at = cache.fetched_at
        assert fetched_at is not None
        assert market_service.is_fresh(cache, settings, fetched_at)
        later = fetched_at + timedelta(days=settings.cache_max_age_days)
        assert not market_service.is_fresh(cache, settings, later)
        cache.last_error = "http_402"
        assert not market_service.is_fresh(cache, settings, fetched_at)
    assert not market_service.is_fresh(None, settings, fetched_at)


@pytest.mark.parametrize("text", ["Not over 63,000 Baht", "ไม่เกิน 45,000 บาท", "up to 50,000"])
def test_a_ceiling_is_not_an_exact_salary(text: str) -> None:
    assert market.parse_salary(text) is None
