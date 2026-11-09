"""The admin dashboard's numbers (Contract.md §2.9, Design.md §4.8, PRD FR-40 – FR-45).

Only SELECTs, and only counts, rates and per-role rows: no query reads CV text, chat text, answers,
emails or the names users typed (FR-41, FR-42).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import iso, to_bangkok, utcnow
from app.core.config import Settings
from app.domain import admin_stats
from app.domain.admin_stats import percentile, share
from app.domain.chat_answers import load_salary_reference
from app.domain.matching.roles import load_catalogue
from app.infra.jev import JEV_TASKS
from app.infra.models import (
    Answer,
    CvDocument,
    EditProposal,
    JobPosting,
    LlmCall,
    Profile,
    QuotaUsage,
    RefreshLog,
    RemovedSkill,
    RequestLog,
    RoleCache,
    RouterLog,
    User,
)
from app.router.llm_decision import MIN_CONFIDENCE
from app.services import cv_service, market_service, quota_service

Window = Literal["today", "7d", "30d"]

OVERVIEW_ROUTE = "/api/admin/overview"
_CV_UPLOAD_ROUTE = "/api/cv"
_ROLE_VIEW_ROUTE = "/api/roles/{role_id}"
_NEAR_LIMIT = 0.8  # FR-43c
_TOP_REMOVED = 5


def _start_of_day(day: date, tz: str) -> datetime:
    # In UTC: SQLite drops the offset, so every stored time and every bound must be UTC.
    return datetime.combine(day, time.min, ZoneInfo(tz)).astimezone(UTC)


def _window_start(window: Window, now: datetime, tz: str) -> datetime:
    if window == "today":
        return _start_of_day(quota_service.quota_day(now, tz), tz)
    return now - timedelta(days=7 if window == "7d" else 30)


# Jev answers in about 0.3 s and has its own limits, so it must not skew the Groq figures.
_IS_GROQ = LlmCall.task.not_in(JEV_TASKS)


async def _count(db: AsyncSession, *conditions: ColumnElement[bool], of: Any) -> int:
    return await db.scalar(select(func.count()).select_from(of).where(*conditions)) or 0


async def _health(db: AsyncSession, start: datetime) -> dict[str, Any]:
    # The page refreshes itself every 60 s, which would bury the requests users make.
    counted = and_(RequestLog.created_at >= start, RequestLog.route != OVERVIEW_ROUTE)
    requests = await _count(db, counted, of=RequestLog)
    failed = await _count(db, counted, RequestLog.status >= 500, of=RequestLog)
    codes = await db.execute(
        select(RequestLog.code, func.count())
        .where(counted, RequestLog.code.is_not(None))
        .group_by(RequestLog.code)
        .order_by(func.count().desc(), RequestLog.code)
    )
    latencies = list(
        await db.scalars(
            select(LlmCall.latency_ms)
            .where(LlmCall.created_at >= start, _IS_GROQ)
            .order_by(LlmCall.latency_ms)
        )
    )
    last = await db.scalar(select(func.max(RequestLog.created_at)).where(counted))
    return {
        "api": "ok",
        "db": "ok",  # the login check has just read the database
        "last_request_at": iso(last) if last else None,
        "requests": requests,
        "error_rate": share(failed, requests),
        "errors_by_code": [{"code": code, "count": count} for code, count in codes],
        "llm_latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "target": admin_stats.LLM_LATENCY_TARGET_MS,
        },
    }


async def _llm(db: AsyncSession, settings: Settings, day: date, start: datetime) -> dict[str, Any]:
    today = LlmCall.created_at >= start
    used = {
        model: (tokens, requests)
        for model, tokens, requests in await db.execute(
            select(
                LlmCall.model,
                func.sum(LlmCall.prompt_tokens + LlmCall.completion_tokens),
                func.count(),
            )
            .where(today)
            .group_by(LlmCall.model)
        )
    }
    # Groq's limits are per model, so a model used in two roles is one row, named by its main use.
    roles = {
        settings.groq_fallback_model: "fallback",
        settings.groq_router_model: "router",
        settings.groq_model: "main",
    }
    order = {"main": 0, "router": 1, "fallback": 2}
    models = [
        {
            "model": model,
            "role": role,
            "tokens_used": int(used.get(model, (0, 0))[0]),
            "tokens_limit": settings.groq_daily_token_limit,
            "requests_used": used.get(model, (0, 0))[1],
            "requests_limit": settings.groq_daily_request_limit,
        }
        for model, role in sorted(roles.items(), key=lambda item: order[item[1]])
        if model
    ]
    return {
        "day": day.isoformat(),
        "models": models,
        "rate_limited_429": await _count(
            db, today, _IS_GROQ, LlmCall.outcome == "rate_limited", of=LlmCall
        ),
        "fallback_calls": await _count(db, today, LlmCall.fallback_used.is_(True), of=LlmCall),
        "jev": await _jev(db, today),
    }


async def _jev(db: AsyncSession, today: ColumnElement[bool]) -> dict[str, int]:
    is_jev = LlmCall.task.in_(JEV_TASKS)
    tokens = await db.scalar(select(func.sum(LlmCall.prompt_tokens)).where(today, is_jev))
    return {
        "calls": await _count(db, today, is_jev, of=LlmCall),
        "failed": await _count(db, today, is_jev, LlmCall.outcome != "ok", of=LlmCall),
        "input_tokens": int(tokens or 0),
    }


async def _quota(db: AsyncSession, settings: Settings, day: date) -> dict[str, Any]:
    today = QuotaUsage.day == day
    requests, tokens = settings.quota_daily_requests, settings.quota_daily_tokens
    totals = (
        await db.execute(
            select(func.sum(QuotaUsage.requests), func.sum(QuotaUsage.tokens)).where(today)
        )
    ).one()
    exhausted = or_(QuotaUsage.requests >= requests, QuotaUsage.tokens >= tokens)
    near = or_(
        QuotaUsage.requests >= requests * _NEAR_LIMIT, QuotaUsage.tokens >= tokens * _NEAR_LIMIT
    )
    return {
        "requests_used": int(totals[0] or 0),
        "tokens_used": int(totals[1] or 0),
        "users_active": await _count(db, today, QuotaUsage.requests > 0, of=QuotaUsage),
        "users_exhausted": await _count(db, today, exhausted, of=QuotaUsage),
        "users_over_80pct": await _count(db, today, near, of=QuotaUsage),
    }


async def _cache(db: AsyncSession, settings: Settings, now: datetime) -> dict[str, Any]:
    caches = {row.role_id: row for row in await db.scalars(select(RoleCache))}
    has_salary = or_(JobPosting.salary_min.is_not(None), JobPosting.salary_max.is_not(None))
    postings = {
        role_id: (count, parsed)
        for role_id, count, parsed in await db.execute(
            select(JobPosting.role_id, func.count(), func.count(case((has_salary, 1)))).group_by(
                JobPosting.role_id
            )
        )
    }
    references = load_salary_reference(settings.data_dir)
    rows = []
    for role in load_catalogue(settings.data_dir):
        cache = caches.get(role.role_id)
        fetched_at = cache.fetched_at if cache else None
        count, parsed = postings.get(role.role_id, (0, 0))
        rows.append(
            {
                "role_id": role.role_id,
                "title_th": role.title_th,
                "fetched_at": iso(fetched_at) if fetched_at else None,
                "age_days": (to_bangkok(now) - to_bangkok(fetched_at)).days if fetched_at else None,
                "stale": fetched_at is not None
                and not market_service.is_fresh(cache, settings, now),
                "refreshing": cache.refreshing if cache else False,
                "last_error": cache.last_error if cache else None,
                "posting_count": count,
                "salary_parsed_share": share(parsed, count),
                "has_reference_salary": role.role_id in references,
            }
        )
    today = quota_service.quota_day(now, settings.quota_tz)
    monday = today - timedelta(days=today.weekday())
    return {
        "apify_runs_this_week": await _count(db, RefreshLog.day >= monday, of=RefreshLog),
        "apify_runs_budget": settings.apify_weekly_budget,
        "roles": rows,
    }


async def _router(db: AsyncSession, start: datetime) -> dict[str, Any]:
    counted = RouterLog.created_at >= start
    by_route = dict(
        (route, count)
        for route, count in await db.execute(
            select(RouterLog.route, func.count())
            .where(counted)
            .group_by(RouterLog.route)
            .order_by(func.count().desc(), RouterLog.route)
        )
    )
    by_layer = dict(
        (layer, count)
        for layer, count in await db.execute(
            select(RouterLog.layer, func.count()).where(counted).group_by(RouterLog.layer)
        )
    )
    messages = sum(by_route.values())
    low = await _count(db, counted, RouterLog.confidence < MIN_CONFIDENCE, of=RouterLog)
    return {
        "messages": messages,
        "by_route": [
            {"route": route, "share": share(count, messages)} for route, count in by_route.items()
        ],
        "by_layer": {
            layer: share(by_layer.get(layer, 0), messages) for layer in ("rules", "llm", "guard")
        },
        "clarify_rate": share(by_route.get("clarify", 0), messages),
        "decline_rate": share(by_route.get("decline", 0), messages),
        "low_confidence_rate": share(low, messages),
    }


async def _top_removed(
    db: AsyncSession, settings: Settings, start: datetime
) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(RemovedSkill.skill_id, func.count())
        .where(RemovedSkill.removed_at >= start)
        .group_by(RemovedSkill.skill_id)
        .order_by(func.count().desc(), RemovedSkill.skill_id)
    )
    # Names come from the taxonomy: a skill outside it was typed by a user (FR-42).
    taxonomy = cv_service.taxonomy_for(settings)
    known = [(taxonomy.get(skill_id), count) for skill_id, count in rows]
    return [
        {"skill_id": skill.id, "name_th": skill.name_th, "count": count}
        for skill, count in known
        if skill is not None
    ][:_TOP_REMOVED]


async def _funnel(
    db: AsyncSession, settings: Settings, start: datetime, now: datetime
) -> dict[str, Any]:
    """The first steps follow the users who registered in the window; the rest are window events."""
    joined = User.created_at >= start
    with_cv = User.id.in_(select(CvDocument.user_id))
    with_answers = User.id.in_(select(Answer.user_id))
    with_profile = User.id.in_(select(Profile.user_id))
    opened_role = User.id.in_(
        select(RequestLog.user_id).where(
            RequestLog.route == _ROLE_VIEW_ROUTE, RequestLog.status == 200
        )
    )
    cv_only = await _count(db, joined, with_cv, ~with_answers, of=User)
    answers_only = await _count(db, joined, ~with_cv, with_answers, of=User)
    both = await _count(db, joined, with_cv, with_answers, of=User)
    with_input = cv_only + answers_only + both

    uploads = and_(
        RequestLog.created_at >= start,
        RequestLog.route == _CV_UPLOAD_ROUTE,
        RequestLog.method == "POST",
    )
    unreadable = await _count(db, uploads, RequestLog.code == "CV_UNREADABLE", of=RequestLog)
    uploaded = await _count(db, uploads, RequestLog.status == 200, of=RequestLog) + unreadable
    average = await db.scalar(
        select(func.avg(Profile.completeness_at_generate)).where(Profile.generated_at >= start)
    )

    proposed = EditProposal.created_at >= start
    lapsed = and_(EditProposal.status == "pending", EditProposal.expires_at <= now)
    return {
        "registered": await _count(db, joined, of=User),
        "with_cv_or_questionnaire": with_input,
        "profile_generated": await _count(db, joined, with_profile, of=User),
        "role_opened": await _count(db, joined, opened_role, of=User),
        "cv_unreadable_rate": share(unreadable, uploaded),
        "input_mix": {
            "cv_only": share(cv_only, with_input),
            "questionnaire_only": share(answers_only, with_input),
            "both": share(both, with_input),
        },
        "avg_completeness_at_generate": round(float(average), 1) if average is not None else 0,
        "edits": {
            "applied": await _count(
                db, proposed, EditProposal.status == "applied", of=EditProposal
            ),
            "rejected": await _count(
                db, proposed, EditProposal.status == "rejected", of=EditProposal
            ),
            # Nothing marks a proposal nobody came back to, so its time decides.
            "expired": await _count(
                db, proposed, or_(EditProposal.status == "expired", lapsed), of=EditProposal
            ),
        },
        "top_removed_skills": await _top_removed(db, settings, start),
    }


async def overview(db: AsyncSession, settings: Settings, *, window: Window) -> dict[str, Any]:
    now = utcnow()
    tz = settings.quota_tz
    day = quota_service.quota_day(now, tz)
    start = _window_start(window, now, tz)
    health = await _health(db, start)
    llm = await _llm(db, settings, day, _start_of_day(day, tz))
    cache = await _cache(db, settings, now)
    return {
        "generated_at": iso(now),
        "window": window,
        "warnings": admin_stats.warnings(
            health=health,
            llm_models=llm["models"],
            cache=cache,
            llm_pct=settings.admin_warn_llm_pct,
            error_pct=settings.admin_warn_error_pct,
            max_age_days=settings.cache_max_age_days,
        ),
        "health": health,
        "llm": llm,
        "quota": await _quota(db, settings, day),
        "cache": cache,
        "router": await _router(db, start),
        "funnel": await _funnel(db, settings, start, now),
    }
