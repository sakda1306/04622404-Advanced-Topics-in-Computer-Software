"""The shared job cache: fill it per role and read it (Design.md §4.4, §7, PRD FR-21 – FR-22f).

Only the seed and the scheduled refresh call the provider; reading never does. A failed fetch keeps
the previous data and records why (FR-22b). Every call to the provider adds a `refresh_log` row,
because each one costs credit and counts toward the weekly budget (FR-22c).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import iso, to_bangkok, utcnow
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.domain import market
from app.domain.chat_answers import SalaryRow, load_salary_reference
from app.domain.matching.roles import RoleProfile, load_catalogue
from app.domain.matching.skills import SkillTaxonomy
from app.infra.models import JobPosting, RefreshLog, RoleCache
from app.providers.base import JobDataProvider, Posting, ProviderError

POSTINGS_PER_ROLE = 20  # FR-22c: 26 runs and about 520 results per week
_SOURCE_NAMES = {"jobthai": "JobThai"}
DISCLAIMER_TH = "ข้อมูลประกาศงานรวบรวมจากแหล่งที่ไม่เป็นทางการ อาจไม่ครบถ้วน"  # DesignSystem.md §5


@dataclass(frozen=True, slots=True)
class RefreshResult:
    role_id: str
    ok: bool
    fetched: int = 0  # what the provider returned, which is what the run costs
    kept: int = 0  # Bangkok postings that fit the role
    not_bangkok: int = 0
    not_the_role: int = 0
    levels: dict[str, int] = field(default_factory=dict)  # kept postings per stated level
    error: str | None = None


def is_fresh(cache: RoleCache | None, settings: Settings, now: datetime) -> bool:
    if cache is None or cache.fetched_at is None or cache.last_error:
        return False
    return to_bangkok(now) - to_bangkok(cache.fetched_at) < timedelta(
        days=settings.cache_max_age_days
    )


def _row(posting: Posting, role_id: str, fetched_at: datetime) -> JobPosting:
    salary = market.parse_salary(posting.salary_text)
    return JobPosting(
        role_id=role_id,
        source=posting.source,
        title=posting.title,
        company=posting.company,
        location=posting.location,
        salary_text=posting.salary_text or None,
        salary_min=salary.min_thb if salary else None,
        salary_max=salary.max_thb if salary else None,
        salary_period=salary.period if salary else None,
        posted_at=market.parse_posted_at(posting.posted_text),
        url=posting.url,
        fetched_at=fetched_at,
    )


async def _set_refreshing(db: AsyncSession, role_id: str) -> RoleCache:
    cache = await db.get(RoleCache, role_id, populate_existing=True)
    if cache is None:
        cache = RoleCache(role_id=role_id, refreshing=True)
        db.add(cache)
    else:
        cache.refreshing = True
    await db.commit()
    return cache


async def _finish_failed(
    db: AsyncSession, cache: RoleCache, role_id: str, code: str, now: datetime
) -> RefreshResult:
    await db.rollback()
    cache.refreshing = False
    cache.last_error = code
    db.add(RefreshLog(day=to_bangkok(now).date(), role_id=role_id, status="failed"))
    await db.commit()
    return RefreshResult(role_id, ok=False, error=code)


async def refresh_role(
    db: AsyncSession,
    provider: JobDataProvider,
    role: RoleProfile,
    *,
    searches: dict[str, market.RoleSearch],
    taxonomy: SkillTaxonomy,
    limit: int = POSTINGS_PER_ROLE,
) -> RefreshResult:
    cache = await _set_refreshing(db, role.role_id)
    now = utcnow()
    try:
        fetched = await provider.fetch_postings(searches[role.role_id].keyword, limit)
    except ProviderError as exc:
        return await _finish_failed(db, cache, role.role_id, exc.code, now)
    except Exception:
        await _finish_failed(db, cache, role.role_id, "unexpected", now)
        raise
    if not fetched:  # a broken scraper looks the same, so do not wipe what we have
        return await _finish_failed(db, cache, role.role_id, "no_results", now)

    seen: set[str] = set()
    kept: list[Posting] = []
    not_bangkok = not_the_role = 0
    for posting in fetched:
        if posting.url in seen:
            continue
        seen.add(posting.url)
        if not market.is_bangkok(posting):
            not_bangkok += 1
        elif not market.fits_role(posting, role, searches, taxonomy):
            not_the_role += 1
        else:
            kept.append(posting)

    rows = [_row(posting, role.role_id, now) for posting in kept]
    salaries = [
        market.Salary(row.salary_min, row.salary_max, row.salary_period)
        for row in rows
        if row.salary_min is not None and row.salary_max is not None and row.salary_period
    ]
    await db.execute(delete(JobPosting).where(JobPosting.role_id == role.role_id))
    db.add_all(rows)
    cache.fetched_at = now
    cache.refreshing = False
    cache.last_error = None
    cache.demand = market.demand(kept, taxonomy)
    cache.salary_advertised = market.advertised_range(salaries, to_bangkok(now).date())
    db.add(RefreshLog(day=to_bangkok(now).date(), role_id=role.role_id, status="ok"))
    await db.commit()
    levels = Counter(market.job_level(posting.title) or "unstated" for posting in kept)
    return RefreshResult(
        role.role_id,
        ok=True,
        fetched=len(fetched),
        kept=len(kept),
        not_bangkok=not_bangkok,
        not_the_role=not_the_role,
        levels=dict(levels),
    )


def _reference(row: SalaryRow | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "min_thb": row.min_thb,
        "max_thb": row.max_thb,
        "measure": "monthly_base",
        "source": row.source,
        "source_type": "curated_reference",
        "as_of": row.published_at,
        "url": row.url,
    }


def _listing(posting: JobPosting) -> dict[str, Any]:
    """Contract.md `Listing`: optional fields are left out, and there are no contact fields."""
    listing: dict[str, Any] = {
        "title": posting.title,
        "company": posting.company,
        "url": posting.url,
        "source": _SOURCE_NAMES.get(posting.source, posting.source),
    }
    if posting.location:
        listing["location"] = posting.location
    if posting.salary_text:
        listing["salary_text"] = posting.salary_text
    if posting.posted_at:
        listing["posted_at"] = posting.posted_at.isoformat()
    return listing


async def role_market(
    db: AsyncSession, role_id: str, settings: Settings, *, listings: int
) -> dict[str, Any]:
    """Contract.md `RoleMarket`, from the cache only (FR-22b).

    `baseline` stays null until the NSO figure is in /data: a wage with no source is not shown.
    """
    if not any(role.role_id == role_id for role in load_catalogue(settings.data_dir)):
        raise AppError(ErrorCode.ROLE_NOT_FOUND)
    cache = await db.get(RoleCache, role_id)
    available = cache is not None and cache.fetched_at is not None
    rows: list[JobPosting] = []
    if available and listings:
        query = (
            select(JobPosting)
            .where(JobPosting.role_id == role_id)
            .order_by(JobPosting.posted_at.is_(None), JobPosting.posted_at.desc(), JobPosting.title)
            .limit(listings)
        )
        rows = list(await db.scalars(query))
    return {
        "role_id": role_id,
        "location_scope": "bangkok",
        "available": available,
        "fetched_at": iso(cache.fetched_at) if available else None,
        "stale": available and not is_fresh(cache, settings, utcnow()),
        "refreshing": cache.refreshing if cache is not None else False,
        "salary": {
            "advertised": cache.salary_advertised if available else None,
            "reference": _reference(load_salary_reference(settings.data_dir).get(role_id)),
            "baseline": None,
        },
        "demand": cache.demand if available else None,
        "listings": [_listing(row) for row in rows],
        "disclaimer_th": DISCLAIMER_TH,
    }
