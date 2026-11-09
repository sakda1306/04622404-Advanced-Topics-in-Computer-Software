"""GET /api/roles/{role_id}/market (Contract.md §2.7, PRD FR-21 – FR-22f)."""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from app.api.deps import Container
from app.core.clock import utcnow
from app.infra.models import JobPosting, RoleCache
from tests.conftest import assert_problem

ROLE = "qa-engineer"
ADVERTISED = {
    "min_thb": 30000,
    "max_thb": 50000,
    "measure": "monthly_base",
    "source": "JobThai (ประกาศงาน)",
    "source_type": "advertised",
    "sample_size": 1,
    "as_of": "2026-11-03",
}
DEMAND = {
    "posting_count": 3,
    "trending_skills": [{"skill_id": "sql", "name_th": "SQL", "count": 2}],
}


def _posting(title: str, posted_at: date | None, **fields: object) -> JobPosting:
    values: dict[str, object] = {
        "role_id": ROLE,
        "source": "jobthai",
        "title": title,
        "company": "บริษัทตัวอย่าง",
        "location": "กรุงเทพมหานคร",
        "salary_text": None,
        "posted_at": posted_at,
        "url": f"https://www.jobthai.com/th/job/{title}",
        "fetched_at": utcnow(),
    }
    return JobPosting(**{**values, **fields})


async def _seed(container: Container, **cache: object) -> None:
    values: dict[str, object] = {
        "role_id": ROLE,
        "fetched_at": utcnow(),
        "demand": DEMAND,
        "salary_advertised": ADVERTISED,
    }
    async with container.sessions() as db:
        db.add(RoleCache(**{**values, **cache}))
        db.add_all(
            [
                _posting("old", date(2026, 10, 1)),
                _posting("no-date", None),
                _posting("new", date(2026, 11, 1), salary_text="30,000 - 50,000 บาท"),
            ]
        )
        await db.commit()


async def test_the_market_needs_a_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get(f"/api/roles/{ROLE}/market"), 401, "UNAUTHENTICATED")


async def test_an_unknown_role_is_not_found(user: httpx.AsyncClient) -> None:
    assert_problem(await user.get("/api/roles/no-such-role/market"), 404, "ROLE_NOT_FOUND")


async def test_no_cache_yet_is_a_200_that_says_so(user: httpx.AsyncClient) -> None:
    response = await user.get(f"/api/roles/{ROLE}/market")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["refreshing"] is False
    assert body["stale"] is False
    assert body["fetched_at"] is None
    assert body["demand"] is None
    assert body["listings"] == []
    assert body["location_scope"] == "bangkok"
    assert body["disclaimer_th"]


async def test_a_first_fetch_still_running_is_refreshing(
    user: httpx.AsyncClient, container: Container
) -> None:
    await _seed(container, fetched_at=None, refreshing=True, demand=None, salary_advertised=None)
    body = (await user.get(f"/api/roles/{ROLE}/market")).json()
    assert body["available"] is False
    assert body["refreshing"] is True
    assert body["listings"] == []


async def test_the_cache_gives_every_layer_and_the_newest_listings(
    user: httpx.AsyncClient, container: Container
) -> None:
    await _seed(container)
    body = (await user.get(f"/api/roles/{ROLE}/market", params={"listings": 2})).json()
    assert body["available"] is True
    assert body["stale"] is False
    assert body["fetched_at"] is not None
    assert body["salary"]["advertised"] == ADVERTISED
    assert body["demand"] == DEMAND
    reference = body["salary"]["reference"]
    assert reference["source_type"] == "curated_reference"
    assert reference["min_thb"] == 22000
    assert reference["measure"] == "monthly_base"
    assert reference["url"].startswith("https://")
    assert body["salary"]["baseline"] is None
    assert [listing["title"] for listing in body["listings"]] == ["new", "old"]
    assert body["listings"][0] == {
        "title": "new",
        "company": "บริษัทตัวอย่าง",
        "location": "กรุงเทพมหานคร",
        "salary_text": "30,000 - 50,000 บาท",
        "posted_at": "2026-11-01",
        "url": "https://www.jobthai.com/th/job/new",
        "source": "JobThai",
    }
    assert "salary_text" not in body["listings"][1]


async def test_a_listing_with_no_date_comes_last(
    user: httpx.AsyncClient, container: Container
) -> None:
    await _seed(container)
    body = (await user.get(f"/api/roles/{ROLE}/market", params={"listings": 20})).json()
    assert [listing["title"] for listing in body["listings"]] == ["new", "old", "no-date"]
    assert "posted_at" not in body["listings"][2]


async def test_a_role_with_no_fitting_postings_is_available_and_empty(
    user: httpx.AsyncClient, container: Container
) -> None:
    async with container.sessions() as db:
        db.add(
            RoleCache(
                role_id=ROLE,
                fetched_at=utcnow(),
                demand={"posting_count": 0, "trending_skills": []},
                salary_advertised=None,
            )
        )
        await db.commit()
    body = (await user.get(f"/api/roles/{ROLE}/market")).json()
    assert body["available"] is True
    assert body["salary"]["advertised"] is None
    assert body["demand"]["posting_count"] == 0
    assert body["listings"] == []


async def test_old_data_is_stale(user: httpx.AsyncClient, container: Container) -> None:
    await _seed(container, fetched_at=utcnow() - timedelta(days=8))
    body = (await user.get(f"/api/roles/{ROLE}/market")).json()
    assert body["available"] is True
    assert body["stale"] is True


async def test_a_failed_refresh_keeps_the_data_and_is_stale(
    user: httpx.AsyncClient, container: Container
) -> None:
    await _seed(container, last_error="timeout")
    body = (await user.get(f"/api/roles/{ROLE}/market")).json()
    assert body["stale"] is True
    assert body["salary"]["advertised"] == ADVERTISED
    assert len(body["listings"]) == 3


async def test_listings_zero_and_too_many(user: httpx.AsyncClient, container: Container) -> None:
    await _seed(container)
    body = (await user.get(f"/api/roles/{ROLE}/market", params={"listings": 0})).json()
    assert body["listings"] == []
    response = await user.get(f"/api/roles/{ROLE}/market", params={"listings": 21})
    assert response.status_code == 422
