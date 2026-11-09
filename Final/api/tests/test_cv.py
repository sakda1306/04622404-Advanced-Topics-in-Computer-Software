"""CV endpoints (Contract.md §2.2, PRD FR-0 – FR-4)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.api.deps import Container
from app.core.clock import utcnow
from app.infra.models import CvDocument, Profile
from tests.conftest import ClientFactory, assert_problem, register
from tests.pdf_fixtures import make_pdf
from tests.test_cv_parser import CV_EN


async def _upload(
    client: httpx.AsyncClient, data: bytes, name: str = "cv.pdf", ctype: str = "application/pdf"
) -> httpx.Response:
    return await client.post("/api/cv", files={"file": (name, data, ctype)})


async def test_upload_returns_draft(user: httpx.AsyncClient) -> None:
    response = await _upload(user, make_pdf(CV_EN), name="../../My CV.pdf")
    assert response.status_code == 200, response.text
    cv = response.json()["cv"]
    assert cv["status"] == "draft"
    assert cv["filename"] == "My CV.pdf"
    assert {"python", "docker"} <= {s["skill_id"] for s in cv["skills"]}
    assert cv["experience"][0]["title"] == "Backend Developer"
    assert cv["education"][0]["school"] == "Kasetsart University"
    assert isinstance(cv["warnings_th"], list)
    # No LLM extraction yet, so no quota is used (Contract §2.2: counts only if the LLM runs).
    assert response.headers["x-quota-requests-remaining"] == "40"


async def test_get_cv(user: httpx.AsyncClient) -> None:
    assert (await user.get("/api/cv")).json() == {"cv": None}
    await _upload(user, make_pdf(CV_EN))
    assert (await user.get("/api/cv")).json()["cv"]["status"] == "draft"


async def test_new_upload_replaces_the_old_one(
    container: Container, user: httpx.AsyncClient
) -> None:
    await _upload(user, make_pdf(CV_EN), name="old.pdf")
    await _upload(user, make_pdf(CV_EN), name="new.pdf")
    assert (await user.get("/api/cv")).json()["cv"]["filename"] == "new.pdf"
    async with container.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(CvDocument)) == 1


@pytest.mark.parametrize(
    ("data", "name", "ctype"),
    [
        (b"hello", "cv.pdf", "application/pdf"),  # not PDF bytes
        (make_pdf(CV_EN), "cv.docx", "application/vnd.openxmlformats"),
    ],
)
async def test_not_a_pdf(user: httpx.AsyncClient, data: bytes, name: str, ctype: str) -> None:
    assert_problem(await _upload(user, data, name, ctype), 415, "CV_INVALID_TYPE")


@pytest.mark.parametrize("settings_overrides", [{"cv_max_bytes": 900}])
async def test_too_large(user: httpx.AsyncClient) -> None:
    # Over the limit but inside the multipart allowance, so the route itself must check.
    data = make_pdf(["x" * 40] * 8)
    assert len(data) > 900
    assert_problem(await _upload(user, data), 413, "CV_TOO_LARGE")


async def test_scanned_pdf(user: httpx.AsyncClient) -> None:
    body = assert_problem(await _upload(user, make_pdf(None)), 422, "CV_UNREADABLE")
    assert "แบบสอบถาม" in body["message_th"]


async def test_missing_file_field(user: httpx.AsyncClient) -> None:
    response = await user.post("/api/cv", files={"other": ("cv.pdf", b"%PDF", "application/pdf")})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_cv_needs_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/api/cv"), 401, "UNAUTHENTICATED")
    assert_problem(await _upload(client, make_pdf(CV_EN)), 401, "UNAUTHENTICATED")


CONFIRM: dict[str, Any] = {
    "skills": [
        {"name": "Python", "skill_id": "python", "level": 3, "line_no": 4},
        {"name": "Docker", "skill_id": "docker", "level": 2, "line_no": 4},
        {"name": "FastAPI", "level": 2, "line_no": 7},
    ],
    "education": [{"school": "Kasetsart University", "degree": "Bachelor of Engineering"}],
    "experience": [{"title": "Backend Developer", "company": "Acme", "start": "2022-01"}],
}


async def test_confirm_saves_and_returns_completeness(user: httpx.AsyncClient) -> None:
    await _upload(user, make_pdf(CV_EN))
    response = await user.put("/api/cv/confirm", json=CONFIRM)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cv"]["status"] == "confirmed"
    assert [s["name"] for s in body["cv"]["skills"]] == ["Python", "Docker", "FastAPI"]
    assert body["cv"]["warnings_th"] == []
    assert body["completeness"]["score"] == 60
    assert body["completeness"]["missing_required"] == []
    assert (await user.get("/api/cv")).json()["cv"]["status"] == "confirmed"


async def test_confirm_without_cv(user: httpx.AsyncClient) -> None:
    assert_problem(await user.put("/api/cv/confirm", json=CONFIRM), 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "change",
    [
        {"skills": [{"name": "X", "skill_id": "not-a-skill", "level": 2, "line_no": 1}]},
        {"skills": [{"name": "X", "level": 5, "line_no": 1}]},
        {"skills": [{"name": "", "level": 2, "line_no": 1}]},
        {"education": [{"degree": "BSc"}]},
        {"experience": [{"title": "Dev", "salary": 1}]},
    ],
)
async def test_confirm_validation(user: httpx.AsyncClient, change: dict[str, Any]) -> None:
    await _upload(user, make_pdf(CV_EN))
    response = await user.put("/api/cv/confirm", json={**CONFIRM, **change})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_delete_cv(user: httpx.AsyncClient) -> None:
    await _upload(user, make_pdf(CV_EN))
    await user.put("/api/cv/confirm", json=CONFIRM)
    response = await user.delete("/api/cv")
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["completeness"]["score"] == 0
    assert (await user.get("/api/cv")).json() == {"cv": None}
    assert (await user.delete("/api/cv")).status_code == 200  # nothing left: still fine


async def test_one_user_cannot_see_another_users_cv(client_factory: ClientFactory) -> None:
    a, b = client_factory(), client_factory()
    await register(a, email="a@example.com")
    await register(b, email="b@example.com")
    await _upload(a, make_pdf(CV_EN))
    assert (await b.get("/api/cv")).json() == {"cv": None}


async def test_account_delete_removes_cv(
    container: Container, client_factory: ClientFactory
) -> None:
    c = client_factory()
    await register(c, email="gone@example.com")
    await _upload(c, make_pdf(CV_EN))
    await c.request("DELETE", "/api/me", json={"confirm": "DELETE"})
    async with container.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(CvDocument)) == 0


# --- found by testing the running system


def _profile_row(user_id: str, sections: dict[str, Any]) -> Profile:
    now = utcnow()
    return Profile(
        user_id=user_id, sections=sections, profile_version=1, generated_at=now, updated_at=now
    )


async def test_deleting_a_cv_keeps_a_profile_that_never_used_one(
    container: Container, user: httpx.AsyncClient
) -> None:
    me = (await user.get("/api/auth/me")).json()["user"]["id"]
    sections = {"evidence": {"answer-go_salary": {"id": "answer-go_salary", "kind": "answer"}}}
    async with container.sessions() as db:
        db.add(_profile_row(me, sections))
        await db.commit()
    assert (await user.delete("/api/cv")).status_code == 200
    async with container.sessions() as db:
        assert await db.get(Profile, me) is not None


async def test_deleting_a_cv_removes_a_profile_that_quotes_it(
    container: Container, user: httpx.AsyncClient
) -> None:
    me = (await user.get("/api/auth/me")).json()["user"]["id"]
    sections = {"evidence": {"cv-1": {"id": "cv-1", "kind": "cv_line"}}}
    async with container.sessions() as db:
        db.add(_profile_row(me, sections))
        await db.commit()
    assert (await user.delete("/api/cv")).status_code == 200
    async with container.sessions() as db:
        assert await db.get(Profile, me) is None


async def test_confirm_works_out_months_from_the_dates(user: httpx.AsyncClient) -> None:
    await _upload(user, make_pdf(CV_EN))
    body = {
        "skills": [],
        "education": [],
        "experience": [
            {"title": "Edited", "start": "2022-01", "end": "2022-12", "months": 5, "line_no": 0},
            {"title": "Added", "start": "2023-01", "end": "2023-03", "line_no": 0},
            {"title": "No dates", "months": 7, "line_no": 0},
        ],
    }
    response = await user.put("/api/cv/confirm", json=body)
    assert response.status_code == 200, response.text
    months = [e.get("months") for e in response.json()["cv"]["experience"]]
    assert months == [12, 3, 7]


async def test_an_unchanged_draft_passes_its_own_confirm(user: httpx.AsyncClient) -> None:
    long_title = "Backend Developer " + "x" * 200
    jobs = [f"{long_title} Jan 20{10 + i % 9} - Feb 20{10 + i % 9}" for i in range(35)]
    lines = ["Experience", *jobs, "Education", "(Example University)"]
    uploaded = await _upload(user, make_pdf(lines))
    assert uploaded.status_code == 200, uploaded.text
    cv = uploaded.json()["cv"]
    body = {key: cv[key] for key in ("skills", "education", "experience")}
    response = await user.put("/api/cv/confirm", json=body)
    assert response.status_code == 200, response.text
