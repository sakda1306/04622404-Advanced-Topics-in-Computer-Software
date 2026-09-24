"""
Integration tests against the REAL Postgres/Redis started by
`docker compose up`. Run these with:

    docker compose exec app pytest tests/test_db_integration.py -v

They are skipped (not failed) if the database is unreachable, so they
never break a plain `pytest` run on a laptop without Docker running.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from app import db, feedback as feedback_module
from app.mock_data import ALL_SCENARIOS
from app.schema import FeedbackCategory, FeedbackSubmission


async def _db_reachable() -> bool:
    try:
        await db.wait_for_db(retries=1, delay_seconds=0)
        return True
    except Exception:
        return False


@pytest_asyncio.fixture   # เปลี่ยนจาก @pytest.fixture
async def require_db():
    if not await _db_reachable():
        pytest.skip("Postgres is not reachable — run `docker compose up -d` first")


@pytest.mark.asyncio
async def test_save_and_fetch_recommendation(require_db):
    scenario = ALL_SCENARIOS["travel_normally"].model_copy(
        update={"request_id": f"test-{uuid4()}"}
    )
    await db.save_recommendation(scenario, pseudonymous_user_id="anon-test-1")
    stored = await db.get_recommendation(scenario.request_id)
    assert stored is not None
    assert stored["request_id"] == scenario.request_id


@pytest.mark.asyncio
async def test_unsafe_feedback_appears_in_safety_queue(require_db):
    scenario = ALL_SCENARIOS["avoid_travel"].model_copy(
        update={"request_id": f"test-{uuid4()}"}
    )
    fb = FeedbackSubmission(
        request_id=scenario.request_id,
        pseudonymous_user_id="anon-test-2",
        category=FeedbackCategory.UNSAFE,
        comment="integration test - unsafe report",
        submitted_at=datetime.now(timezone.utc),
    )
    # avoid_travel scenario must exist in recommendation_log first (FK constraint)
    await db.save_recommendation(scenario, pseudonymous_user_id="anon-test-2")

    escalated = await feedback_module.submit_feedback(fb)
    assert escalated is True

    pending = await feedback_module.pending_safety_review()
    assert any(item["request_id"] == fb.request_id for item in pending)


@pytest.mark.asyncio
async def test_reviewed_feedback_moves_to_training_set(require_db):
    scenario = ALL_SCENARIOS["change_route"].model_copy(
        update={"request_id": f"test-{uuid4()}"}
    )
    fb = FeedbackSubmission(
        request_id=scenario.request_id,
        pseudonymous_user_id="anon-test-3",
        category=FeedbackCategory.INCORRECT,
        submitted_at=datetime.now(timezone.utc),
    )
    await db.save_recommendation(scenario, pseudonymous_user_id="anon-test-3")
    await feedback_module.submit_feedback(fb)

    before = await feedback_module.reviewed_for_training()
    assert not any(item["request_id"] == fb.request_id for item in before)

    await feedback_module.mark_reviewed(fb.request_id, reviewer="ops-alice")

    after = await feedback_module.reviewed_for_training()
    assert any(item["request_id"] == fb.request_id for item in after)
