"""Database-level rules: CHECK constraints, cascades, PostGIS and partitioning."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.infrastructure.db.models import (
    AuditLogModel,
    ConversationModel,
    CoverageAreaModel,
    FeedbackModel,
    JobModel,
    MessageModel,
    RecommendationModel,
    TravelRequestModel,
    TripModel,
    UserModel,
)
from app.infrastructure.db.reference_data import seed_reference_data
from tests.integration import factories as f

pytestmark = pytest.mark.integration


async def _expect_violation(session: AsyncSession, constraint: str, *rows: Any) -> None:
    async with session.begin_nested():
        session.add_all(rows)
        with pytest.raises(IntegrityError, match=constraint):
            await session.flush()


@pytest.fixture
async def owner(session: AsyncSession) -> UserModel:
    user = f.user()
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def make_request(
    session: AsyncSession, owner: UserModel
) -> Callable[..., Awaitable[TravelRequestModel]]:
    async def _make(**overrides: Any) -> TravelRequestModel:
        request = f.travel_request(owner, **overrides)
        session.add(request)
        await session.flush()
        return request

    return _make


# ------------------------------------------------------------------ CHECK constraints


async def test_high_risk_can_never_be_travel_normally(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    request = await make_request()
    row = f.recommendation(owner, request, risk_level="HIGH", recommendation_type="TRAVEL_NORMALLY")

    await _expect_violation(session, "ck_recommendations_no_travel_normally_on_high_risk", row)


async def test_high_risk_with_avoid_travel_is_allowed(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    request = await make_request()
    session.add(
        f.recommendation(owner, request, risk_level="HIGH", recommendation_type="AVOID_TRAVEL")
    )

    await session.flush()


async def test_completed_recommendation_needs_payload(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    request = await make_request()
    row = f.recommendation(owner, request, payload=None)

    await _expect_violation(session, "ck_recommendations_completed_has_payload", row)


async def test_python_none_is_stored_as_sql_null_in_json_columns(
    session: AsyncSession, owner: UserModel
) -> None:
    # JSON 'null' would satisfy NOT NULL; the column type must write SQL NULL instead.
    await _expect_violation(session, "preferences", f.travel_request(owner, preferences=None))


async def test_processing_recommendation_may_have_no_result_yet(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    request = await make_request()
    session.add(
        f.recommendation(
            owner,
            request,
            status="processing",
            payload=None,
            risk_level=None,
            recommendation_type=None,
        )
    )

    await session.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"risk_score": 1.5}, "ck_recommendations_risk_score_range"),
        ({"risk_confidence": -0.1}, "ck_recommendations_risk_confidence_range"),
        ({"status": "done"}, "ck_recommendations_status"),
        ({"risk_level": "EXTREME"}, "ck_recommendations_risk_level"),
        ({"recommendation_type": "GO"}, "ck_recommendations_recommendation_type"),
    ],
)
async def test_recommendation_value_checks(
    session: AsyncSession,
    owner: UserModel,
    make_request: Callable[..., Awaitable[Any]],
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    request = await make_request()

    await _expect_violation(session, constraint, f.recommendation(owner, request, **overrides))


async def test_one_recommendation_per_request(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    request = await make_request()
    session.add(f.recommendation(owner, request))
    await session.flush()

    await _expect_violation(
        session, "uq_recommendations_request_id", f.recommendation(owner, request)
    )


async def test_request_source_and_mode_checks(session: AsyncSession, owner: UserModel) -> None:
    await _expect_violation(
        session, "ck_travel_requests_source", f.travel_request(owner, source="WEB")
    )
    await _expect_violation(
        session, "ck_travel_requests_mode", f.travel_request(owner, mode="fast")
    )


async def test_trip_alerts_require_consent(session: AsyncSession, owner: UserModel) -> None:
    row = f.trip(owner, alerts_enabled=True, alerts_consent_at=None)

    await _expect_violation(session, "ck_trips_alerts_need_consent", row)


async def test_trip_alerts_with_consent_are_allowed(
    session: AsyncSession, owner: UserModel
) -> None:
    session.add(f.trip(owner, alerts_enabled=True, alerts_consent_at=f.later(0)))

    await session.flush()


async def test_job_must_target_exactly_one_resource(
    session: AsyncSession, owner: UserModel
) -> None:
    row = JobModel(user_id=owner.id, type="RECOMMENDATION", expires_at=f.later())

    await _expect_violation(session, "ck_jobs_single_target", row)


async def test_job_progress_range(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    request = await make_request()
    reco = f.recommendation(owner, request, status="processing", payload=None)
    session.add(reco)
    await session.flush()
    row = JobModel(
        user_id=owner.id,
        type="RECOMMENDATION",
        recommendation_id=reco.id,
        progress=101,
        expires_at=f.later(),
    )

    await _expect_violation(session, "ck_jobs_progress_range", row)


async def test_message_role(session: AsyncSession, owner: UserModel) -> None:
    conv = f.conversation(owner)
    session.add(conv)
    await session.flush()

    await _expect_violation(
        session,
        "ck_messages_role",
        MessageModel(conversation_id=conv.id, role="system", content="hi"),
    )
    # The content is encrypted, so its 4,000-character limit is checked by the
    # application (MESSAGE_MAX_CHARS), not by the database (D-81).


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"rating": 6}, "ck_feedback_rating_range"),
        ({"usable_for_training": True}, "ck_feedback_training_needs_approval"),
        ({"report_type": "SPAM"}, "ck_feedback_report_type"),
        ({"review_status": "maybe"}, "ck_feedback_review_status"),
    ],
)
async def test_feedback_checks(
    session: AsyncSession, overrides: dict[str, Any], constraint: str
) -> None:
    row = FeedbackModel(
        recommendation_id=new_id(),
        pseudonymous_id="p-1",
        expires_at=f.later(180),
        **overrides,
    )

    await _expect_violation(session, constraint, row)


async def test_approved_feedback_can_be_used_for_training(session: AsyncSession) -> None:
    session.add(
        FeedbackModel(
            recommendation_id=new_id(),
            pseudonymous_id="p-1",
            review_status="approved",
            usable_for_training=True,
            expires_at=f.later(180),
        )
    )

    await session.flush()


async def test_oidc_identity_is_unique(session: AsyncSession, owner: UserModel) -> None:
    duplicate = f.user(oidc_subject=owner.oidc_subject)

    await _expect_violation(session, "uq_users_oidc_identity", duplicate)


async def test_server_defaults_are_applied(session: AsyncSession, owner: UserModel) -> None:
    await session.refresh(owner)

    assert owner.language == "th"
    assert owner.timezone == "Asia/Bangkok"
    assert owner.consent_analytics is False
    assert owner.created_at is not None
    assert owner.id.version == 7


# ------------------------------------------------------------------ cascades


async def _count(session: AsyncSession, model: Any, **filters: Any) -> int:
    stmt = select(func.count()).select_from(model).filter_by(**filters)
    return int((await session.execute(stmt)).scalar_one())


async def test_deleting_a_user_removes_their_data(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    conv = f.conversation(owner)
    trip = f.trip(owner)
    session.add_all([conv, trip])
    await session.flush()
    request = await make_request(conversation_id=conv.id, trip_id=trip.id)
    reco = f.recommendation(owner, request, conversation_id=conv.id, trip_id=trip.id)
    session.add(reco)
    await session.flush()
    session.add_all(
        [
            MessageModel(conversation_id=conv.id, role="user", content="safe?"),
            JobModel(
                user_id=owner.id,
                type="RECOMMENDATION",
                recommendation_id=reco.id,
                expires_at=f.later(),
            ),
        ]
    )
    await session.flush()

    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner.id})

    for model in (
        ConversationModel,
        TripModel,
        TravelRequestModel,
        RecommendationModel,
        JobModel,
    ):
        assert await _count(session, model, user_id=owner.id) == 0, model.__tablename__
    assert await _count(session, MessageModel, conversation_id=conv.id) == 0


async def test_deleting_a_recommendation_keeps_references_as_null(
    session: AsyncSession, owner: UserModel, make_request: Callable[..., Awaitable[Any]]
) -> None:
    conv = f.conversation(owner)
    session.add(conv)
    await session.flush()
    request = await make_request(conversation_id=conv.id)
    reco = f.recommendation(owner, request, conversation_id=conv.id)
    session.add(reco)
    await session.flush()
    message = MessageModel(
        conversation_id=conv.id, role="assistant", content="ok", recommendation_id=reco.id
    )
    session.add(message)
    await session.execute(
        text(
            "UPDATE conversations SET last_recommendation_id = :r, last_request_id = :q "
            "WHERE id = :c"
        ),
        {"r": reco.id, "q": request.id, "c": conv.id},
    )
    await session.flush()

    await session.execute(text("DELETE FROM travel_requests WHERE id = :id"), {"id": request.id})

    row = (
        await session.execute(
            text("SELECT last_recommendation_id, last_request_id FROM conversations WHERE id = :c"),
            {"c": conv.id},
        )
    ).one()
    assert tuple(row) == (None, None)
    kept = (
        await session.execute(
            text("SELECT recommendation_id FROM messages WHERE id = :m"), {"m": message.id}
        )
    ).scalar_one()
    assert kept is None


# ------------------------------------------------------------------ PostGIS


async def test_coverage_area_contains_bangkok_but_not_tokyo(session: AsyncSession) -> None:
    await seed_reference_data(session)

    async def covered(lon_lat: tuple[float, float]) -> bool:
        stmt = select(func.ST_Covers(CoverageAreaModel.area, f.point(lon_lat))).where(
            CoverageAreaModel.code == "TH"
        )
        return bool((await session.execute(stmt)).scalar_one())

    assert await covered(f.BANGKOK) is True
    assert await covered(f.TOKYO) is False


async def test_trip_points_support_distance_in_metres(
    session: AsyncSession, owner: UserModel
) -> None:
    trip = f.trip(owner)
    session.add(trip)
    await session.flush()

    stmt = select(func.ST_Distance(TripModel.origin, TripModel.destination)).where(
        TripModel.id == trip.id
    )
    metres = float((await session.execute(stmt)).scalar_one())

    # Bangkok to Chiang Mai is about 590 km in a straight line.
    assert 570_000 < metres < 610_000


async def test_invalid_srid_is_rejected(session: AsyncSession, owner: UserModel) -> None:
    from geoalchemy2 import WKTElement

    row = f.trip(owner, origin=WKTElement("POINT(100 13)", srid=3857))

    async with session.begin_nested():
        session.add(row)
        with pytest.raises(Exception, match="SRID"):
            await session.flush()


# ------------------------------------------------------------------ audit log partition


async def test_audit_rows_go_to_a_partition(session: AsyncSession) -> None:
    session.add(
        AuditLogModel(
            actor_type="system",
            actor_ref="purge",
            action="retention.purge",
            result="success",
            correlation_id="corr-1",
            metadata_={"deleted": 3},
        )
    )
    await session.flush()

    partition = (
        await session.execute(
            text("SELECT tableoid::regclass::text FROM audit_logs WHERE actor_ref = 'purge'")
        )
    ).scalar_one()
    assert partition == "audit_logs_default"


# ------------------------------------------------------------------ seed data


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    first = await seed_reference_data(session)
    second = await seed_reference_data(session)

    assert first == second == {"coverage_areas": 1, "emergency_defaults": 2}
    rows = (
        await session.execute(
            text(
                "SELECT region_code, language, instructions -> 'contacts' -> 0 ->> 'phone' "
                "FROM emergency_defaults ORDER BY language"
            )
        )
    ).all()
    assert [tuple(r) for r in rows] == [("TH", "en", "191"), ("TH", "th", "191")]
