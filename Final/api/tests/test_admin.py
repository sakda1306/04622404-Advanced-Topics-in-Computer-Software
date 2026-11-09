"""The admin dashboard's data (Contract.md §2.9, PRD FR-40 – FR-45)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.api.deps import Container
from app.core.clock import utcnow
from app.domain.admin_stats import percentile, share
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
from app.services import quota_service
from app.services.log_cleanup import delete_old_logs
from tests.conftest import ClientFactory, assert_problem, register
from tests.test_profile import LLM_SECTIONS, Groq, _ready

URL = "/api/admin/overview"


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {
        "admin_emails": ["admin@example.com"],
        "groq_api_key": "k",
        "groq_model": "main-model",
        "groq_router_model": "router-model",
        "groq_fallback_model": "router-model",
        "quota_daily_requests": 10,
        "quota_daily_tokens": 1000,
        "data_dir": "../data",
    }


@pytest.fixture
async def admin(client_factory: ClientFactory) -> httpx.AsyncClient:
    c = client_factory()
    await register(c, "admin@example.com")
    return c


def _today(container: Container) -> date:
    return quota_service.quota_day(utcnow(), container.settings.quota_tz)


async def _user_id(container: Container, email: str = "admin@example.com") -> str:
    async with container.sessions() as db:
        user_id = await db.scalar(select(User.id).where(User.email == email))
    assert user_id is not None
    return user_id


async def _seed(container: Container, *rows: Any) -> None:
    async with container.sessions() as db:
        db.add_all(rows)
        await db.commit()


def _request(route: str = "/api/quota", status: int = 200, **values: Any) -> RequestLog:
    return RequestLog(
        request_id="r", method="GET", route=route, status=status, latency_ms=5, **values
    )


def _llm(model: str = "main-model", latency: int = 100, **values: Any) -> LlmCall:
    return LlmCall(
        **{
            "task": "profile",
            "model": model,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "latency_ms": latency,
            "outcome": "ok",
            "fallback_used": False,
            **values,
        }
    )


def _route(route: str = "salary", layer: str = "rules", confidence: float = 0.9, **v: Any) -> Any:
    return lambda user_id: RouterLog(
        user_id=user_id,
        route=route,
        layer=layer,
        confidence=confidence,
        latency_ms=1,
        tokens=0,
        **v,
    )


def _posting(role_id: str, salary_min: int | None = None) -> JobPosting:
    return JobPosting(
        role_id=role_id,
        source="jobthai",
        title="t",
        company="c",
        location="l",
        salary_min=salary_min,
        url="https://example.com",
        fetched_at=utcnow(),
    )


async def _get(admin: httpx.AsyncClient, window: str = "today") -> dict[str, Any]:
    response = await admin.get(URL, params={"window": window})
    assert response.status_code == 200, response.text
    return response.json()


# --- who can see it


async def test_needs_a_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get(URL), 401, "UNAUTHENTICATED")


async def test_other_accounts_are_forbidden(user: httpx.AsyncClient) -> None:
    assert_problem(await user.get(URL), 403, "FORBIDDEN")


async def test_an_unknown_window_is_refused(admin: httpx.AsyncClient) -> None:
    assert_problem(await admin.get(URL, params={"window": "1y"}), 422, "VALIDATION_ERROR")


async def test_defaults_to_today_and_works_with_little_data(admin: httpx.AsyncClient) -> None:
    response = await admin.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["window"] == "today"
    assert body["warnings"] == []
    assert body["generated_at"].endswith("+07:00")
    assert body["router"]["messages"] == 0
    assert body["router"]["by_layer"] == {"rules": 0, "llm": 0, "guard": 0}
    assert body["health"]["llm_latency_ms"] == {"p50": 0, "p95": 0, "target": 15000}
    assert body["funnel"]["edits"] == {"applied": 0, "rejected": 0, "expired": 0}
    assert body["funnel"]["avg_completeness_at_generate"] == 0


# --- health


async def test_health_counts_requests_and_errors(
    container: Container, admin: httpx.AsyncClient
) -> None:
    before = (await _get(admin))["health"]["requests"]
    await _seed(
        container,
        _request(status=503, code="LLM_UNAVAILABLE"),
        _request(status=503, code="LLM_UNAVAILABLE"),
        _request(status=504, code="LLM_TIMEOUT"),
        _request(status=404, code="ROLE_NOT_FOUND"),
        *[_request() for _ in range(6)],
    )
    health = (await _get(admin))["health"]
    assert health["requests"] == before + 10
    assert health["error_rate"] == share(3, before + 10)
    assert health["errors_by_code"][0] == {"code": "LLM_UNAVAILABLE", "count": 2}
    assert {"code": "ROLE_NOT_FOUND", "count": 1} in health["errors_by_code"]
    assert health["last_request_at"].endswith("+07:00")


async def test_the_dashboard_does_not_count_its_own_refreshes(admin: httpx.AsyncClient) -> None:
    first = (await _get(admin))["health"]["requests"]
    await _get(admin)
    await _get(admin)
    assert (await _get(admin))["health"]["requests"] == first


async def test_the_window_decides_what_counts(
    container: Container, admin: httpx.AsyncClient
) -> None:
    now = utcnow()
    await _seed(
        container,
        _request(created_at=now - timedelta(days=2)),
        _request(created_at=now - timedelta(days=20)),
        _request(created_at=now - timedelta(days=40)),
        _llm(latency=7000, created_at=now - timedelta(days=2)),
    )
    today = (await _get(admin, "today"))["health"]
    week = (await _get(admin, "7d"))["health"]
    month = (await _get(admin, "30d"))["health"]
    assert week["requests"] == today["requests"] + 1
    assert month["requests"] == today["requests"] + 2
    assert today["llm_latency_ms"]["p50"] == 0
    assert week["llm_latency_ms"]["p50"] == 7000


async def test_llm_latency_percentiles(container: Container, admin: httpx.AsyncClient) -> None:
    await _seed(container, *[_llm(latency=ms * 100) for ms in range(1, 21)])
    latency = (await _get(admin))["health"]["llm_latency_ms"]
    assert latency == {"p50": 1000, "p95": 1900, "target": 15000}


def test_percentile_and_share() -> None:
    assert percentile([], 50) == 0
    assert percentile([7], 95) == 7
    assert percentile([1, 2, 3, 4], 50) == 2
    assert share(1, 0) == 0
    assert share(1, 3) == 0.333


async def test_a_high_error_rate_warns(container: Container, admin: httpx.AsyncClient) -> None:
    await _seed(container, *[_request(status=500, code="INTERNAL_ERROR") for _ in range(3)])
    warnings = (await _get(admin))["warnings"]
    assert [w["code"] for w in warnings] == ["ERROR_RATE_HIGH"]
    assert warnings[0]["panel"] == "health"


# --- LLM usage


async def test_llm_usage_is_per_model_and_only_today(
    container: Container, admin: httpx.AsyncClient
) -> None:
    await _seed(
        container,
        _llm(),
        _llm(),
        _llm(model="router-model"),
        _llm(model="router-model", fallback_used=True),
        _llm(outcome="rate_limited", prompt_tokens=0, completion_tokens=0),
        _llm(created_at=utcnow() - timedelta(days=2)),
    )
    llm = (await _get(admin, "30d"))["llm"]
    assert llm["day"] == _today(container).isoformat()
    # The router and the fallback share a model, and Groq's limit is per model.
    assert llm["models"] == [
        {
            "model": "main-model",
            "role": "main",
            "tokens_used": 30,
            "tokens_limit": 200_000,
            "requests_used": 3,
            "requests_limit": 1_000,
        },
        {
            "model": "router-model",
            "role": "router",
            "tokens_used": 30,
            "tokens_limit": 200_000,
            "requests_used": 2,
            "requests_limit": 1_000,
        },
    ]
    assert llm["rate_limited_429"] == 1
    assert llm["fallback_calls"] == 1


def _jev(**values: Any) -> LlmCall:
    fields = {"model": "jev-1.14.0", "task": "router_jev", "prompt_tokens": 600}
    return _llm(**{**fields, "completion_tokens": 0, "latency": 250, **values})


async def test_jev_calls_are_counted_apart_from_groq(
    container: Container, admin: httpx.AsyncClient
) -> None:
    await _seed(
        container,
        _llm(latency=9_000),
        _jev(),
        _jev(outcome="rate_limited", prompt_tokens=0),
        _jev(outcome="timeout", prompt_tokens=0),
        _jev(created_at=utcnow() - timedelta(days=2)),
    )
    body = await _get(admin)
    assert body["llm"]["jev"] == {"calls": 3, "failed": 2, "input_tokens": 600}
    assert body["llm"]["rate_limited_429"] == 0
    assert body["health"]["llm_latency_ms"]["p50"] == 9_000


async def test_the_work_style_question_to_jev_counts_as_jev(
    container: Container, admin: httpx.AsyncClient
) -> None:
    await _seed(container, _llm(latency=9_000), _jev(task="work_style_jev", latency=250))
    body = await _get(admin)
    assert body["llm"]["jev"] == {"calls": 1, "failed": 0, "input_tokens": 600}
    assert body["health"]["llm_latency_ms"]["p50"] == 9_000


async def test_a_model_near_its_limit_warns(container: Container, admin: httpx.AsyncClient) -> None:
    await _seed(container, _llm(prompt_tokens=170_000, completion_tokens=0))
    warnings = (await _get(admin))["warnings"]
    assert [(w["panel"], w["code"]) for w in warnings] == [("llm", "LLM_NEAR_LIMIT")]
    assert "main-model" in warnings[0]["message_th"]
    assert "85%" in warnings[0]["message_th"]


@pytest.mark.parametrize(
    "settings_overrides",
    [
        {
            "admin_emails": ["admin@example.com"],
            "groq_model": "main-model",
            "groq_router_model": "router-model",
            "groq_fallback_model": "backup-model",
            "admin_warn_llm_pct": 90,
            "data_dir": "../data",
        }
    ],
)
async def test_thresholds_and_models_come_from_settings(
    container: Container, admin: httpx.AsyncClient
) -> None:
    await _seed(container, _llm(prompt_tokens=170_000, completion_tokens=0))
    body = await _get(admin)
    assert body["warnings"] == []
    assert [m["role"] for m in body["llm"]["models"]] == ["main", "router", "fallback"]


# --- quota


async def test_quota_is_for_today(
    container: Container, client_factory: ClientFactory, admin: httpx.AsyncClient
) -> None:
    ids = []
    for name in ("a", "b", "c", "d"):
        c = client_factory()
        await register(c, f"{name}@example.com")
        ids.append(await _user_id(container, f"{name}@example.com"))
    today = _today(container)
    await _seed(
        container,
        QuotaUsage(user_id=ids[0], day=today, requests=10, tokens=100),  # limit reached
        QuotaUsage(user_id=ids[1], day=today, requests=2, tokens=850),  # over 80%
        QuotaUsage(user_id=ids[2], day=today, requests=1, tokens=50),
        QuotaUsage(user_id=ids[3], day=today - timedelta(days=1), requests=10, tokens=1000),
    )
    assert (await _get(admin, "30d"))["quota"] == {
        "requests_used": 13,
        "tokens_used": 1000,
        "users_active": 3,
        "users_exhausted": 1,
        "users_over_80pct": 2,
    }


# --- job-data cache


async def test_cache_has_one_row_per_role(container: Container, admin: httpx.AsyncClient) -> None:
    now = utcnow()
    await _seed(
        container,
        RoleCache(role_id="web-developer", fetched_at=now - timedelta(days=2)),
        RoleCache(role_id="qa-engineer", fetched_at=now - timedelta(days=8)),
        RoleCache(
            role_id="data-engineer",
            fetched_at=now - timedelta(days=1),
            last_error="PROVIDER_TIMEOUT",
        ),
        RoleCache(role_id="devops-engineer", refreshing=True),
        _posting("web-developer", 30000),
        _posting("web-developer"),
        _posting("web-developer"),
        _posting("web-developer", 40000),
    )
    body = await _get(admin)
    rows = {row["role_id"]: row for row in body["cache"]["roles"]}
    assert len(rows) == 26
    web = rows["web-developer"]
    assert web["age_days"] == 2
    assert web["stale"] is False
    assert web["posting_count"] == 4
    assert web["salary_parsed_share"] == 0.5
    assert web["fetched_at"].endswith("+07:00")
    assert rows["qa-engineer"]["stale"] is True
    assert rows["data-engineer"]["stale"] is True
    assert rows["data-engineer"]["last_error"] == "PROVIDER_TIMEOUT"
    assert rows["devops-engineer"]["refreshing"] is True
    assert rows["devops-engineer"]["age_days"] is None
    assert rows["devops-engineer"]["stale"] is False
    assert isinstance(web["has_reference_salary"], bool)
    assert any(row["has_reference_salary"] for row in rows.values())
    codes = {w["code"] for w in body["warnings"] if w["panel"] == "cache"}
    assert codes == {"CACHE_STALE", "CACHE_ERROR"}


async def test_apify_runs_count_this_week_against_the_budget(
    container: Container, admin: httpx.AsyncClient
) -> None:
    today = _today(container)
    monday = today - timedelta(days=today.weekday())
    await _seed(
        container,
        RefreshLog(day=monday - timedelta(days=1), role_id="x", status="ok"),
        *[RefreshLog(day=monday, role_id="x", status="ok") for _ in range(26)],
    )
    body = await _get(admin)
    assert body["cache"]["apify_runs_this_week"] == 26
    assert body["cache"]["apify_runs_budget"] == 26
    assert body["warnings"] == []
    await _seed(container, RefreshLog(day=today, role_id="x", status="failed"))
    assert [w["code"] for w in (await _get(admin))["warnings"]] == ["APIFY_OVER_BUDGET"]


# --- router


async def test_router_shares(container: Container, admin: httpx.AsyncClient) -> None:
    user_id = await _user_id(container)
    rows = [
        _route("salary"),
        _route("salary"),
        _route("market", "llm", 0.8),
        _route("clarify", "llm", 0.4),
        _route("decline", "guard", 1.0),
        _route("salary", created_at=utcnow() - timedelta(days=2)),
    ]
    await _seed(container, *[row(user_id) for row in rows])
    router = (await _get(admin))["router"]
    assert router["messages"] == 5
    assert router["by_route"][0] == {"route": "salary", "share": 0.4}
    assert {"route": "clarify", "share": 0.2} in router["by_route"]
    assert router["by_layer"] == {"rules": 0.4, "llm": 0.4, "guard": 0.2}
    assert router["clarify_rate"] == 0.2
    assert router["decline_rate"] == 0.2
    assert router["low_confidence_rate"] == 0.2
    assert (await _get(admin, "7d"))["router"]["messages"] == 6


# --- funnel


async def test_the_funnel_follows_real_use(
    container: Container, user: httpx.AsyncClient, admin: httpx.AsyncClient
) -> None:
    groq = Groq(container)
    await _ready(container, user)
    groq.reply(LLM_SECTIONS)
    assert (await user.post("/api/profile/generate")).status_code == 200
    assert (await user.get("/api/roles/web-developer")).status_code == 200
    assert (await user.get("/api/roles/no-such-role")).status_code == 404
    funnel = (await _get(admin))["funnel"]
    assert funnel["registered"] == 2
    assert funnel["with_cv_or_questionnaire"] == 1
    assert funnel["profile_generated"] == 1
    assert funnel["role_opened"] == 1
    assert funnel["input_mix"] == {"cv_only": 0, "questionnaire_only": 0, "both": 1}
    async with container.sessions() as db:
        stored = await db.scalar(select(Profile.completeness_at_generate))
    assert stored is not None and stored > 0
    assert funnel["avg_completeness_at_generate"] == stored


async def test_a_role_view_that_failed_is_not_an_opened_role(
    user: httpx.AsyncClient, admin: httpx.AsyncClient
) -> None:
    assert (await user.get("/api/roles/no-such-role")).status_code == 404
    assert (await _get(admin))["funnel"]["role_opened"] == 0


async def test_the_input_mix_and_the_unreadable_rate(
    container: Container, client_factory: ClientFactory, admin: httpx.AsyncClient
) -> None:
    ids = []
    for name in ("a", "b", "c"):
        await register(client_factory(), f"{name}@example.com")
        ids.append(await _user_id(container, f"{name}@example.com"))
    upload = {"route": "/api/cv", "method": "POST"}
    await _seed(
        container,
        CvDocument(user_id=ids[0], filename="x.pdf", text_lines=[], parsed={}),
        Answer(user_id=ids[1], question_id="q", value=1),
        CvDocument(user_id=ids[2], filename="x.pdf", text_lines=[], parsed={}),
        Answer(user_id=ids[2], question_id="q", value=1),
        RequestLog(request_id="r", status=200, latency_ms=1, **upload),
        RequestLog(request_id="r", status=200, latency_ms=1, **upload),
        RequestLog(request_id="r", status=200, latency_ms=1, **upload),
        RequestLog(request_id="r", status=422, code="CV_UNREADABLE", latency_ms=1, **upload),
        RequestLog(request_id="r", status=415, code="CV_INVALID_TYPE", latency_ms=1, **upload),
    )
    funnel = (await _get(admin))["funnel"]
    assert funnel["with_cv_or_questionnaire"] == 3
    assert funnel["input_mix"] == {"cv_only": 0.333, "questionnaire_only": 0.333, "both": 0.333}
    assert funnel["cv_unreadable_rate"] == 0.25


async def test_edits_and_removed_skills(container: Container, admin: httpx.AsyncClient) -> None:
    user_id = await _user_id(container)
    now = utcnow()
    later, past = now + timedelta(minutes=15), now - timedelta(minutes=1)

    def edit(status: str, expires_at: Any, **values: Any) -> EditProposal:
        return EditProposal(
            user_id=user_id,
            changes=[],
            summary_th="s",
            status=status,
            expires_at=expires_at,
            **values,
        )

    def removed(skill_id: str) -> RemovedSkill:
        return RemovedSkill(user_id=user_id, skill_id=skill_id, skill={}, removed_at=now)

    await _seed(
        container,
        edit("applied", later),
        edit("applied", later),
        edit("rejected", later),
        edit("expired", past),
        edit("pending", past),  # nobody came back to it
        edit("pending", later),  # still waiting
        removed("docker"),
        removed("custom-abc123"),
    )
    funnel = (await _get(admin))["funnel"]
    assert funnel["edits"] == {"applied": 2, "rejected": 1, "expired": 2}
    assert [s["skill_id"] for s in funnel["top_removed_skills"]] == ["docker"]
    assert funnel["top_removed_skills"][0]["count"] == 1
    assert funnel["top_removed_skills"][0]["name_th"]


async def test_the_most_removed_skills_are_the_top_five(
    container: Container, client_factory: ClientFactory, admin: httpx.AsyncClient
) -> None:
    ids = [await _user_id(container)]
    await register(client_factory(), "b@example.com")
    ids.append(await _user_id(container, "b@example.com"))
    now = utcnow()
    skills = ["python", "sql", "git", "docker", "html", "css"]
    rows = [
        RemovedSkill(user_id=ids[0], skill_id=skill, skill={}, removed_at=now) for skill in skills
    ]
    rows.append(RemovedSkill(user_id=ids[1], skill_id="sql", skill={}, removed_at=now))
    await _seed(container, *rows)
    top = (await _get(admin))["funnel"]["top_removed_skills"]
    assert len(top) == 5
    assert (top[0]["skill_id"], top[0]["count"]) == ("sql", 2)


# --- aggregates only, read-only


async def test_no_user_content_reaches_the_response(
    container: Container, client_factory: ClientFactory, admin: httpx.AsyncClient
) -> None:
    await register(client_factory(), "secret.person@example.com")
    user_id = await _user_id(container, "secret.person@example.com")
    now = utcnow()
    await _seed(
        container,
        CvDocument(
            user_id=user_id, filename="secret.pdf", text_lines=["SECRET-CV-LINE"], parsed={}
        ),
        Answer(user_id=user_id, question_id="ss_example", value="SECRET-ANSWER"),
        RemovedSkill(
            user_id=user_id,
            skill_id="custom-abc",
            skill={"name_th": "SECRET-SKILL"},
            removed_at=now,
        ),
    )
    text = (await admin.get(URL)).text
    for secret in ("secret.person", "admin@example.com", "SECRET", user_id, "ผู้ใช้"):
        assert secret not in text


async def test_reading_changes_nothing_and_calls_nothing(
    container: Container, admin: httpx.AsyncClient
) -> None:
    async def counts() -> list[int]:
        async with container.sessions() as db:
            tables = (LlmCall, QuotaUsage, RouterLog, RoleCache, RefreshLog, EditProposal)
            return [await db.scalar(select(func.count()).select_from(t)) or 0 for t in tables]

    before = await counts()
    await _get(admin, "30d")
    assert await counts() == before


# --- log cleanup


async def test_old_logs_are_deleted(container: Container, admin: httpx.AsyncClient) -> None:
    now = utcnow()
    days = container.settings.log_retention_days
    await _seed(
        container,
        _request(route="/old", created_at=now - timedelta(days=days + 1)),
        _request(route="/kept", created_at=now - timedelta(days=days - 1)),
        _llm(task="old", created_at=now - timedelta(days=days + 1)),
        _llm(task="kept", created_at=now - timedelta(days=days - 1)),
    )
    async with container.sessions() as db:
        await delete_old_logs(db, container.settings, now)
        routes = set(await db.scalars(select(RequestLog.route)))
        tasks = set(await db.scalars(select(LlmCall.task)))
    assert "/old" not in routes
    assert "/kept" in routes
    assert tasks == {"kept"}
