"""Role catalogue, scoring and endpoints (Contract.md §2.6, Design.md §4.3, FR-18 – FR-20)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.api.deps import Container
from app.domain.matching.roles import Requirement, RoleProfile, load_catalogue
from app.domain.matching.scoring import match_list, score_role
from app.domain.matching.skills import load_taxonomy
from app.infra.llm import GroqClient
from tests.conftest import ClientFactory, assert_problem, register
from tests.test_profile import CV_PARSED, LLM_SECTIONS, _ready

TAXONOMY = load_taxonomy("../data")
CATALOGUE = load_catalogue("../data")
TRAITS = {"teamwork", "structure", "ambiguity", "pressure", "innovation", "leadership"}


def _role(**overrides: Any) -> RoleProfile:
    fields: dict[str, Any] = {
        "role_id": "test-role",
        "title_th": "ทดสอบ",
        "title_en": "Test",
        "career_stage": "entry",
        "required": [
            Requirement(skills=("python",), min_level=2, weight=3),
            Requirement(skills=("sql",), min_level=2, weight=1),
        ],
        "nice_to_have": ("docker", "git"),
        "soft_skills": ("teamwork", "communication"),
        "work_style": {"teamwork": 1.0, "structure": 0.0},
        "description_th": "คำอธิบาย",
        "learning_path_th": "แนวทาง",
        "author": "a",
        "reviewer": "b",
        "status": "draft",
        "sources": [],
    }
    return RoleProfile(**{**fields, **overrides})


def _profile(
    hard: dict[str, int] | None = None,
    soft: list[str] | None = None,
    traits: dict[str, float] | None = None,
) -> dict[str, Any]:
    def skill(skill_id: str, level: int) -> dict[str, Any]:
        known = TAXONOMY.get(skill_id)
        return {
            "skill_id": skill_id,
            "name_th": known.name_th if known else skill_id,
            "level": level,
            "evidence_ids": [f"e-{skill_id}"],
        }

    return {
        "profile_version": 3,
        "hard_skills": [skill(i, level) for i, level in (hard or {}).items()],
        "soft_skills": [skill(i, 2) for i in (soft or [])],
        "preferences": {"work_style": traits or {}},
    }


def _score(role: RoleProfile, profile: dict[str, Any]) -> Any:
    return score_role(role, profile, TAXONOMY)


# --- the catalogue


def test_all_26_roles_load_in_the_listed_order() -> None:
    assert len(CATALOGUE) == 26
    listed = json.loads(Path("../data/roles.json").read_text(encoding="utf-8"))
    assert [r.role_id for r in CATALOGUE] == [r["id"] for r in listed]


@pytest.mark.parametrize("role", CATALOGUE, ids=lambda r: r.role_id)
def test_role_data_can_be_scored(role: RoleProfile) -> None:
    required = [skill for need in role.required for skill in need.skills]
    assert required
    for skill in [*required, *role.nice_to_have]:
        known = TAXONOMY.get(skill)
        assert known is not None and known.type == "hard", skill
    for skill in role.soft_skills:
        known = TAXONOMY.get(skill)
        assert known is not None and known.type == "soft", skill
    assert all(need.min_level >= 1 and need.weight >= 1 for need in role.required)
    assert role.nice_to_have
    assert role.soft_skills
    assert set(role.work_style) == TRAITS
    assert all(0 <= value <= 1 for value in role.work_style.values())
    assert role.description_th
    assert role.learning_path_th
    assert "## " not in role.description_th  # the next section did not leak in


def test_description_and_learning_path_come_from_their_own_sections() -> None:
    role = next(r for r in CATALOGUE if r.role_id == "data-engineer")
    assert role.description_th.startswith("สร้างและดูแล pipeline")
    assert role.learning_path_th.startswith("เรียงตามความสำคัญ")


def test_any_of_becomes_a_group() -> None:
    role = next(r for r in CATALOGUE if r.role_id == "data-engineer")
    assert ("python", "java", "scala") in [need.skills for need in role.required]


# --- the formula


def test_nothing_in_common_scores_only_the_neutral_work_style() -> None:
    scored = _score(_role(), _profile())
    assert scored["breakdown"] == {
        "hard_required": 0,
        "hard_nice": 0,
        "soft": 0,
        "work_style": 0.5,
    }
    assert scored["match_pct"] == 3  # round(100 * 0.05 * 0.5)


def test_a_perfect_profile_scores_100() -> None:
    profile = _profile(
        {"python": 4, "sql": 2, "docker": 1, "git": 1},
        ["teamwork", "communication"],
        {"teamwork": 1.0, "structure": 0.0},
    )
    scored = _score(_role(), profile)
    assert scored["match_pct"] == 100
    assert scored["gaps"] == []


def test_required_skills_are_weighted() -> None:
    assert _score(_role(), _profile({"python": 2}))["breakdown"]["hard_required"] == 0.75
    assert _score(_role(), _profile({"sql": 2}))["breakdown"]["hard_required"] == 0.25


def test_a_level_below_the_minimum_gets_part_of_the_weight() -> None:
    scored = _score(_role(), _profile({"python": 1}))
    assert scored["breakdown"]["hard_required"] == 0.375  # 3 * (1 / 2) / 4


def test_a_level_above_the_minimum_adds_nothing_extra() -> None:
    low, high = _profile({"python": 2}), _profile({"python": 4})
    assert _score(_role(), low)["match_pct"] == _score(_role(), high)["match_pct"]


def test_each_part_has_its_weight() -> None:
    role = _role()
    both = _profile({"python": 2, "sql": 2})
    assert _score(role, both)["match_pct"] == 73  # 70 + 2.5 for neutral work style
    nice = _profile({"docker": 1, "git": 1})
    assert _score(role, nice)["match_pct"] == 18  # 15 + 2.5
    soft = _profile(soft=["teamwork", "communication"])
    assert _score(role, soft)["match_pct"] == 13  # 10 + 2.5
    style = _profile(traits={"teamwork": 1.0, "structure": 0.0})
    assert _score(role, style)["match_pct"] == 5


def test_nice_to_have_and_soft_are_shares() -> None:
    scored = _score(_role(), _profile({"docker": 1}, ["teamwork"]))
    assert scored["breakdown"]["hard_nice"] == 0.5
    assert scored["breakdown"]["soft"] == 0.5


def test_an_any_of_group_uses_the_best_level() -> None:
    role = _role(required=[Requirement(skills=("java", "python"), min_level=2, weight=1)])
    scored = _score(role, _profile({"java": 1, "python": 2}))
    assert scored["breakdown"]["hard_required"] == 1
    assert [m["skill_id"] for m in scored["matched"]] == ["python"]
    assert scored["gaps"][0]["kind"] == "soft_skill"


def test_work_style_uses_only_the_traits_the_user_gave() -> None:
    assert _score(_role(), _profile(traits={"teamwork": 0.5}))["breakdown"]["work_style"] == 0.5
    both = _profile(traits={"teamwork": 0.5, "structure": 0.5})
    assert _score(_role(), both)["breakdown"]["work_style"] == 0.5
    near = _profile(traits={"teamwork": 1.0})
    assert _score(_role(), near)["breakdown"]["work_style"] == 1


def test_a_custom_skill_never_counts() -> None:
    profile = _profile({"custom-abc123": 4})
    assert _score(_role(), profile)["match_pct"] == 3


def test_a_soft_skill_is_not_counted_as_hard() -> None:
    role = _role(required=[Requirement(skills=("python",), min_level=1, weight=1)])
    profile = _profile(soft=["python"])
    assert _score(role, profile)["breakdown"]["hard_required"] == 0


# --- matched and gaps


def test_matched_cites_the_profile_evidence() -> None:
    [first, *_] = _score(_role(), _profile({"python": 2}))["matched"]
    assert first["skill_id"] == "python"
    assert first["evidence_ids"] == ["e-python"]
    known = TAXONOMY.get("python")
    assert known is not None
    assert first["name_th"] == known.name_th


def test_matched_includes_nice_to_have_but_not_soft() -> None:
    scored = _score(_role(), _profile({"python": 2, "docker": 1}, ["teamwork"]))
    assert [m["skill_id"] for m in scored["matched"]] == ["python", "docker"]


def test_a_missing_skill_gap() -> None:
    gap = _score(_role(), _profile())["gaps"][0]
    known = TAXONOMY.get("python")
    assert known is not None
    assert gap == {
        "gap_id": "test-role-req-0",
        "kind": "missing_skill",
        "skill_id": "python",
        "name_th": known.name_th,
        "required_level": 2,
    }


def test_a_missing_group_names_every_alternative() -> None:
    role = _role(required=[Requirement(skills=("java", "python"), min_level=2, weight=1)])
    gap = _score(role, _profile())["gaps"][0]
    java, python = TAXONOMY.get("java"), TAXONOMY.get("python")
    assert java is not None and python is not None
    assert gap["name_th"] == f"{java.name_th} / {python.name_th}"
    assert gap["skill_id"] == "java"


def test_a_below_level_gap() -> None:
    scored = _score(_role(), _profile({"python": 1, "sql": 2}))
    gap = scored["gaps"][0]
    assert gap["gap_id"] == "test-role-req-0"
    assert gap["kind"] == "below_level"
    assert (gap["required_level"], gap["user_level"]) == (2, 1)


def test_a_soft_skill_gap() -> None:
    gaps = _score(_role(), _profile({"python": 2, "sql": 2}, ["teamwork"]))["gaps"]
    assert gaps == [
        {
            "gap_id": "test-role-soft-communication",
            "kind": "soft_skill",
            "skill_id": "communication",
            "name_th": TAXONOMY.get("communication").name_th,  # type: ignore[union-attr]
        }
    ]


def test_gaps_run_missing_by_weight_then_below_level_then_soft() -> None:
    role = _role(
        required=[
            Requirement(skills=("sql",), min_level=2, weight=1),
            Requirement(skills=("git",), min_level=2, weight=2),
            Requirement(skills=("python",), min_level=2, weight=3),
            Requirement(skills=("docker",), min_level=2, weight=3),
        ],
    )
    gaps = _score(role, _profile({"git": 1}))["gaps"]
    assert [g["skill_id"] for g in gaps] == [
        "python",
        "docker",
        "sql",
        "git",
        "teamwork",
        "communication",
    ]
    assert [g["kind"] for g in gaps][3:4] == ["below_level"]


def test_wording_fields_are_left_for_the_explain_step() -> None:
    scored = _score(_role(), _profile())
    assert scored["reason_th"] is None
    assert scored["next_steps"] == []
    # True would show a spinner in the web that nothing can finish yet.
    assert scored["explanations_stale"] is False
    assert (scored["role_id"], scored["title_th"]) == ("test-role", "ทดสอบ")


# --- the list


def _catalogue(*scores: tuple[str, tuple[str, ...]]) -> list[RoleProfile]:
    return [
        _role(
            role_id=role_id,
            required=[Requirement(skills=(s,), min_level=1, weight=1) for s in skills],
        )
        for role_id, skills in scores
    ]


def _list(catalogue: list[RoleProfile], profile: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return match_list(
        catalogue, profile, taxonomy=TAXONOMY, **{"threshold": 60, "top_n": 5, **kwargs}
    )


def test_only_roles_at_or_above_the_threshold_are_shown() -> None:
    catalogue = _catalogue(("hit", ("python",)), ("miss", ("rust",)))
    result = _list(catalogue, _profile({"python": 2}))
    assert result["below_threshold"] is False
    assert [r["role_id"] for r in result["roles"]] == ["hit"]
    assert result["threshold"] == 60
    assert result["profile_version"] == 3


def test_exactly_the_threshold_passes() -> None:
    catalogue = _catalogue(("hit", ("python",)))
    pct = _list(catalogue, _profile({"python": 2}))["roles"][0]["match_pct"]
    result = _list(catalogue, _profile({"python": 2}), threshold=pct)
    assert result["below_threshold"] is False
    assert _list(catalogue, _profile({"python": 2}), threshold=pct + 1)["below_threshold"] is True


def test_at_most_top_n_best_first() -> None:
    catalogue = _catalogue(
        ("half", ("python", "rust")),
        ("full", ("python",)),
        ("also", ("python",)),
    )
    result = _list(catalogue, _profile({"python": 2}), threshold=30, top_n=2)
    assert [r["role_id"] for r in result["roles"]] == ["full", "also"]


def test_the_list_sorts_by_match_not_by_required_skills_alone() -> None:
    needs = [Requirement(skills=(s,), min_level=1, weight=1) for s in ("python", "rust")]
    many = [
        Requirement(skills=(s,), min_level=1, weight=1)
        for s in ("python", "docker", "git", "rust", "java")
    ]
    catalogue = [
        _role(role_id="wide", required=many, nice_to_have=("go",)),  # required 0.60, match 45
        _role(role_id="nice", required=needs, nice_to_have=("docker", "git")),  # 0.50, match 53
    ]
    profile = _profile({"python": 1, "docker": 1, "git": 1})
    result = _list(catalogue, profile, threshold=0)
    assert [r["role_id"] for r in result["roles"]] == ["nice", "wide"]


def test_none_passing_returns_the_three_closest() -> None:
    catalogue = _catalogue(
        ("a", ("rust",)),
        ("b", ("python", "rust", "java", "go")),
        ("c", ("python", "rust")),
        ("d", ("python", "rust", "java")),
    )
    result = _list(catalogue, _profile({"python": 2}), threshold=99)
    assert result["below_threshold"] is True
    assert [r["role_id"] for r in result["roles"]] == ["c", "d", "b"]


# --- calibration (Design.md section 10). Written from who the people are, not from the role files.

STUDENT = _profile(
    {"html": 2, "css": 2, "javascript": 2, "python": 2, "sql": 1, "git": 1},
    ["teamwork", "communication"],
    {"teamwork": 0.75, "structure": 0.5, "ambiguity": 0.5, "innovation": 0.75},
)
FULL_STACK = _profile(
    {
        "javascript": 3,
        "typescript": 3,
        "react": 3,
        "html": 3,
        "css": 3,
        "nodejs": 3,
        "sql": 2,
        "postgresql": 2,
        "git": 3,
        "docker": 2,
        "rest-api": 3,
    },
    ["teamwork", "problem-solving", "communication"],
    {"teamwork": 0.75, "structure": 0.5, "ambiguity": 0.5, "innovation": 0.5},
)
ML_DEVELOPER = _profile(
    {
        "python": 3,
        "machine-learning": 3,
        "deep-learning": 3,
        "pytorch": 3,
        "scikit-learn": 3,
        "statistics": 2,
        "sql": 2,
        "git": 2,
        "docker": 1,
    },
    ["analytical-thinking", "problem-solving"],
    {"teamwork": 0.5, "structure": 0.25, "ambiguity": 1.0, "innovation": 1.0},
)
SAMPLES = [
    (
        STUDENT,
        {"web-developer", "frontend-developer", "software-engineer"},
        "network-administrator",
    ),
    (FULL_STACK, {"fullstack-developer"}, "it-support"),
    (ML_DEVELOPER, {"ml-engineer", "data-scientist", "ai-engineer"}, "it-support"),
]
SAMPLE_IDS = ["student", "full-stack", "ml-developer"]


def _all_scores(profile: dict[str, Any]) -> list[dict[str, Any]]:
    scored = [_score(role, profile) for role in CATALOGUE]
    return sorted(scored, key=lambda s: -s["match_pct"])


@pytest.mark.parametrize(("profile", "own", "_other"), SAMPLES, ids=SAMPLE_IDS)
def test_calibration_own_role_is_in_the_top_3_at_60_or_more(
    profile: dict[str, Any], own: set[str], _other: str
) -> None:
    top = _all_scores(profile)[:3]
    assert any(s["role_id"] in own and s["match_pct"] >= 60 for s in top), [
        (s["role_id"], s["match_pct"]) for s in top
    ]


@pytest.mark.parametrize(
    "profile",
    [
        # Decided 3 Nov: the threshold stays at 60, so the student sees only web developer (69).
        pytest.param(STUDENT, id="student"),
        pytest.param(FULL_STACK, id="full-stack"),
        pytest.param(ML_DEVELOPER, id="ml-developer"),
    ],
)
def test_calibration_shows_1_to_5_roles(profile: dict[str, Any]) -> None:
    passing = [(s["role_id"], s["match_pct"]) for s in _all_scores(profile) if s["match_pct"] >= 60]
    assert 1 <= len(passing) <= 5, passing


@pytest.mark.parametrize(("profile", "_own", "other"), SAMPLES, ids=SAMPLE_IDS)
def test_calibration_an_unrelated_role_stays_under_30(
    profile: dict[str, Any], _own: set[str], other: str
) -> None:
    role = next(r for r in CATALOGUE if r.role_id == other)
    assert _score(role, profile)["match_pct"] < 30


# --- the endpoints


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    return {
        "groq_api_key": "k",
        "groq_model": "main-model",
        "groq_router_model": "router-model",
        "groq_fallback_model": "router-model",
        "data_dir": "../data",
    }


@pytest.fixture
def groq(container: Container) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(LLM_SECTIONS)}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 40, "completion_tokens": 10},
            },
        )

    container.llm = GroqClient(
        container.settings, container.sessions, transport=httpx.MockTransport(handler)
    )


async def _generated(container: Container, client: httpx.AsyncClient) -> dict[str, Any]:
    await _ready(container, client)
    response = await client.post("/api/profile/generate")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_catalogue_shape(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/roles")
    assert response.status_code == 200
    roles = response.json()["roles"]
    assert len(roles) == 26
    assert set(roles[0]) == {"role_id", "title_th", "title_en", "summary_th", "career_stage"}
    assert all(r["summary_th"] and "\n" not in r["summary_th"] for r in roles)


async def test_role_endpoints_need_a_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/roles"), 401, "UNAUTHENTICATED")
    assert_problem(await client.get("/api/roles/matches"), 401, "UNAUTHENTICATED")
    assert_problem(await client.get("/api/roles/data-engineer"), 401, "UNAUTHENTICATED")


async def test_generate_returns_real_matches(
    container: Container, user: httpx.AsyncClient, groq: None
) -> None:
    body = await _generated(container, user)
    matches = body["matches"]
    assert matches["profile_version"] == 1
    assert matches["threshold"] == 60
    assert matches["roles"]
    expected = [s["skill_id"] for s in CV_PARSED["skills"]]
    matched = {m["skill_id"] for role in matches["roles"] for m in role["matched"]}
    assert matched <= set(expected)
    pcts = [role["match_pct"] for role in matches["roles"]]
    assert pcts == sorted(pcts, reverse=True)


async def test_get_matches_equals_what_generate_returned(
    container: Container, user: httpx.AsyncClient, groq: None
) -> None:
    body = await _generated(container, user)
    response = await user.get("/api/roles/matches")
    assert response.status_code == 200
    assert response.json() == body["matches"]


async def test_matches_before_a_profile_is_not_found(user: httpx.AsyncClient) -> None:
    assert_problem(await user.get("/api/roles/matches"), 404, "PROFILE_NOT_FOUND")


async def test_matches_use_the_settings(
    container: Container, user: httpx.AsyncClient, groq: None
) -> None:
    await _generated(container, user)
    container.settings = container.settings.model_copy(update={"match_threshold": 100})
    body = (await user.get("/api/roles/matches")).json()
    assert body["threshold"] == 100
    assert body["below_threshold"] is True
    assert len(body["roles"]) == 3


async def test_matches_use_only_my_profile(
    container: Container, client_factory: ClientFactory, groq: None
) -> None:
    first, second = client_factory(), client_factory()
    await register(first, email="user@example.com")
    await register(second, email="b@example.com")
    await _generated(container, first)
    assert_problem(await second.get("/api/roles/matches"), 404, "PROFILE_NOT_FOUND")
    detail = (await second.get("/api/roles/data-engineer")).json()
    assert detail["match"] is None


async def test_role_detail_shape(user: httpx.AsyncClient) -> None:
    response = await user.get("/api/roles/data-engineer")
    assert response.status_code == 200
    body = response.json()
    assert body["match"] is None
    role = body["role"]
    assert role["role_id"] == "data-engineer"
    assert role["career_stage"] == "entry"
    assert role["description_th"]
    assert role["learning_path_th"]
    assert role["status"] == "reviewed"
    assert role["sources"][0]["url"].startswith("http")
    assert role["soft_skills"][0]["name_th"]
    assert role["nice_to_have"][0]["name_th"]
    group = next(r for r in role["required"] if len(r["skills"]) > 1)
    assert {s["skill_id"] for s in group["skills"]} == {"python", "java", "scala"}
    assert all(s["name_th"] for s in group["skills"])
    assert {"min_level", "weight"} <= set(group)


async def test_role_detail_has_my_match_even_below_the_threshold(
    container: Container, user: httpx.AsyncClient, groq: None
) -> None:
    await _generated(container, user)
    body = (await user.get("/api/roles/ux-ui-designer")).json()
    assert body["match"]["role_id"] == "ux-ui-designer"
    assert body["match"]["match_pct"] < 60


async def test_unknown_role_is_not_found(user: httpx.AsyncClient) -> None:
    assert_problem(await user.get("/api/roles/no-such-role"), 404, "ROLE_NOT_FOUND")


async def test_reading_roles_uses_no_quota(
    container: Container, user: httpx.AsyncClient, groq: None
) -> None:
    await _generated(container, user)
    before = (await user.get("/api/quota")).json()["requests_used"]
    await user.get("/api/roles")
    await user.get("/api/roles/matches")
    await user.get("/api/roles/data-engineer")
    assert (await user.get("/api/quota")).json()["requests_used"] == before
