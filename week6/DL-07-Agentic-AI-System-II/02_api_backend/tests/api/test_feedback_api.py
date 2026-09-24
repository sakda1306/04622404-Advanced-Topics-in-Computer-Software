"""HTTP contract of feedback (E-19) and the safety review queue (services are faked)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user, get_feedback_service
from app.api.resources import AppResources
from app.core.config import Settings
from app.core.crypto import keyed_hash
from app.core.ids import new_id
from app.domain.enums import FeedbackOutcome, ReportType, ReviewStatus
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.main import create_app
from tests.api.fakes import USER, FakeFeedback, feedback_record
from tests.support.auth import TokenFactory

REVIEWER = ["safety:review"]


@pytest.fixture
def fake() -> FakeFeedback:
    return FakeFeedback()


@pytest.fixture
def app(settings: Settings, resources: AppResources, fake: FakeFeedback) -> FastAPI:
    application = create_app(settings, resources)
    application.dependency_overrides[get_current_user] = lambda: USER
    application.dependency_overrides[get_feedback_service] = lambda: fake
    return application


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post_headers(token: str, key: str | None = None) -> dict[str, str]:
    return {**bearer(token), "Idempotency-Key": key or str(uuid4())}


def url_for(fake: FakeFeedback) -> str:
    rec = new_id()
    fake.owned.add(rec)
    return f"/v1/recommendations/{rec}/feedback"


async def test_submit_feedback(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback, settings: Settings
) -> None:
    body = {
        "rating": 4,
        "helpful": True,
        "outcome": "FOLLOWED",
        "report_type": None,
        "comment": "ข้อมูลรถไฟตรงดี",
    }

    response = await client.post(url_for(fake), json=body, headers=post_headers(make_token()))

    assert response.status_code == 201, response.text
    data = response.json()
    assert data == {
        "feedback_id": data["feedback_id"],
        "created_at": "2026-09-17T08:00:00Z",
        "review_status": "pending",
    }
    _, raw, kwargs = fake.calls[0]
    assert raw == FeedbackInput(
        rating=4, helpful=True, outcome=FeedbackOutcome.FOLLOWED, comment="ข้อมูลรถไฟตรงดี"
    )
    assert kwargs["correlation_id"]
    assert kwargs["ip_hash"] == keyed_hash(settings.secrets.ip_hash_secret, "127.0.0.1")


async def test_empty_body_uses_defaults(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback
) -> None:
    await client.post(
        url_for(fake), json={"report_type": "UNSAFE_ADVICE"}, headers=post_headers(make_token())
    )

    assert fake.calls[0][1] == FeedbackInput(report_type=ReportType.UNSAFE_ADVICE)


@pytest.mark.parametrize(
    "bad",
    [
        {"rating": "great"},
        {"outcome": "LOVED_IT"},
        {"report_type": "SPAM"},
        {"score": 3},
    ],
)
async def test_bad_feedback_is_422(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback, bad: dict[str, Any]
) -> None:
    response = await client.post(url_for(fake), json=bad, headers=post_headers(make_token()))

    assert response.status_code == 422


async def test_submit_rules(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback
) -> None:
    headers = post_headers(make_token())
    url = url_for(fake)

    first = await client.post(url, json={"rating": 5}, headers=headers)
    replay = await client.post(url, json={"rating": 5}, headers=headers)
    missing = await client.post(
        f"/v1/recommendations/{uuid4()}/feedback",
        json={"rating": 5},
        headers=post_headers(make_token()),
    )
    read_only = await client.post(
        url, json={"rating": 5}, headers=post_headers(make_token(scopes=["travel:read"]))
    )

    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    assert len(fake.calls) == 1
    assert missing.status_code == 404
    assert read_only.status_code == 403


async def test_review_queue_needs_the_reviewer_scope(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    user = await client.get("/v1/admin/feedback/reviews", headers=bearer(make_token()))
    patch = await client.patch(
        f"/v1/admin/feedback/reviews/{uuid4()}",
        json={"status": "approved"},
        headers=bearer(make_token()),
    )

    assert user.status_code == 403
    assert patch.status_code == 403


async def test_list_reviews(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback
) -> None:
    item = feedback_record()
    fake.records[item.id] = item

    response = await client.get(
        "/v1/admin/feedback/reviews?limit=10&cursor=abc",
        headers=bearer(make_token(subject="reviewer-7", scopes=REVIEWER)),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["next_cursor"] == "next-page"
    assert data["items"][0] == {
        "feedback_id": str(item.id),
        "recommendation_id": str(item.recommendation_id),
        "rating": 1,
        "helpful": False,
        "outcome": "UNKNOWN",
        "report_type": "UNSAFE_ADVICE",
        "comment": "Flooded road",
        "review_status": "pending",
        "review_note": None,
        "reviewed_at": None,
        "created_at": "2026-09-17T08:00:00Z",
        "recommendation": {"recommendation": {"summary": "Go"}},
    }
    _, reviewer, kwargs = fake.calls[0]
    assert reviewer == "reviewer-7"
    assert kwargs["status"] is ReviewStatus.PENDING
    assert (kwargs["limit"], kwargs["cursor"]) == (10, "abc")


async def test_list_reviews_by_status(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback
) -> None:
    headers = bearer(make_token(scopes=REVIEWER))

    ok = await client.get("/v1/admin/feedback/reviews?status=approved", headers=headers)
    bad = await client.get("/v1/admin/feedback/reviews?status=APPROVED", headers=headers)

    assert ok.status_code == 200
    assert fake.calls[0][2]["status"] is ReviewStatus.APPROVED
    assert bad.status_code == 422


async def test_review(
    client: httpx.AsyncClient, make_token: TokenFactory, fake: FakeFeedback
) -> None:
    item = feedback_record()
    fake.records[item.id] = item
    headers = bearer(make_token(subject="reviewer-7", scopes=REVIEWER))
    url = f"/v1/admin/feedback/reviews/{item.id}"

    done = await client.patch(url, json={"status": "approved", "note": "ok"}, headers=headers)
    again = await client.patch(url, json={"status": "rejected"}, headers=headers)
    missing = await client.patch(
        f"/v1/admin/feedback/reviews/{uuid4()}", json={"status": "approved"}, headers=headers
    )
    bad = await client.patch(url, json={"status": "pending"}, headers=headers)

    assert done.status_code == 200, done.text
    assert done.json()["review_status"] == "approved"
    assert done.json()["review_note"] == "ok"
    assert "recommendation" not in done.json()
    _, reviewer, kwargs = fake.calls[0]
    assert reviewer == "reviewer-7"
    assert kwargs["decision"] is ReviewDecision.APPROVED
    assert again.status_code == 409
    assert again.json()["code"] == "REVIEW_NOT_PENDING"
    assert missing.status_code == 404
    assert bad.status_code == 422
