"""Database access for the recommendation flow (docs/03_data_design.md sections 3.1-3.8).

Each method runs in its own transaction. Reads take the caller's `user_id`, so another
user's resource looks exactly like a missing one (IDOR, spec section 3).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography, Geometry
from sqlalchemy import and_, cast, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.core.logging import get_logger
from app.domain.enums import (
    JobStage,
    JobStatus,
    JobType,
    MessageRole,
    RecommendationStatus,
    RecommendationType,
    RequestSource,
    RiskLevel,
    job_type_for,
)
from app.domain.normalization import NormalizedTravelRequest
from app.domain.retention import expires_at
from app.domain.sanitizer import truncate
from app.infrastructure.db.models import (
    AgentRunModel,
    ConversationModel,
    CoverageAreaModel,
    EmergencyDefaultModel,
    JobModel,
    MessageModel,
    PredictionRecordModel,
    RecommendationModel,
    TravelRequestModel,
    TripModel,
    UserModel,
)
from app.infrastructure.db.repositories.requests import (
    load_request,
    point_json,
    point_value,
    preferences_json,
)
from app.services.pagination import Cursor
from app.services.ports import (
    CancelOutcome,
    CreatedRecommendation,
    JobOutcome,
    JobRecord,
    NewRecommendation,
    RecommendationRecord,
    RecommendationSummaryRecord,
    StoredResult,
    UserRef,
    WorkItem,
)

log = get_logger(__name__)

MESSAGE_MAX_CHARS = 4000
TITLE_MAX_CHARS = 200
_ACTIVE = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
# A job the reaper closes ran out of time from the user's point of view (D-74).
_STUCK_CODE = "AGENT_TIMEOUT"


def _title(request: NormalizedTravelRequest) -> str | None:
    if request.origin.name and request.destination.name:
        return truncate(f"{request.origin.name} → {request.destination.name}", TITLE_MAX_CHARS)
    return None


def _decimal(value: float | None) -> Decimal | None:
    return Decimal(str(round(value, 3))) if value is not None else None


def user_ref(row: UserModel) -> UserRef:
    return UserRef(
        id=row.id,
        pseudonymous_id=row.pseudonymous_id,
        language=row.language,
        home_region=row.home_region,
        deletion_requested=row.deleted_at is not None,
    )


def summary_record(row: RecommendationModel) -> RecommendationSummaryRecord:
    return RecommendationSummaryRecord(
        id=row.id,
        created_at=row.created_at,
        status=RecommendationStatus(row.status),
        risk_level=RiskLevel(row.risk_level) if row.risk_level else None,
        recommendation_type=(
            RecommendationType(row.recommendation_type) if row.recommendation_type else None
        ),
        origin_name=row.origin_name,
        destination_name=row.destination_name,
        departure_time=row.departure_time,
    )


def _job_record(row: JobModel) -> JobRecord:
    return JobRecord(
        id=row.id,
        user_id=row.user_id,
        type=JobType(row.type),
        status=JobStatus(row.status),
        stage=JobStage(row.stage),
        progress=row.progress,
        recommendation_id=row.recommendation_id,
        error_code=row.error_code,
        created_at=row.created_at,
        updated_at=row.finished_at or row.started_at or row.created_at,
    )


class SqlRecommendationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        return self._sessions

    # ------------------------------------------------------------------ users and lookups

    async def get_or_create_user(
        self, issuer: str, subject: str, *, pseudonym: Callable[[UUID], str]
    ) -> UserRef:
        identity = (UserModel.oidc_issuer == issuer, UserModel.oidc_subject == subject)
        async with self._sessions() as session:
            existing = await session.scalar(select(UserModel).where(*identity))
            if existing is not None:
                return user_ref(existing)
        user_id = new_id()
        async with self._sessions() as session, session.begin():
            await session.execute(
                insert(UserModel)
                .values(
                    id=user_id,
                    oidc_issuer=issuer,
                    oidc_subject=subject,
                    pseudonymous_id=pseudonym(user_id),
                )
                .on_conflict_do_nothing(index_elements=["oidc_issuer", "oidc_subject"])
            )
            # Another request may have created the user first; its row wins.
            row = await session.scalar(select(UserModel).where(*identity))
            assert row is not None
            return user_ref(row)

    async def conversation_exists(self, user_id: UUID, conversation_id: UUID) -> bool:
        async with self._sessions() as session:
            found = await session.scalar(
                select(ConversationModel.id).where(
                    ConversationModel.id == conversation_id, ConversationModel.user_id == user_id
                )
            )
            return found is not None

    async def trip_exists(self, user_id: UUID, trip_id: UUID) -> bool:
        async with self._sessions() as session:
            found = await session.scalar(
                select(TripModel.id).where(TripModel.id == trip_id, TripModel.user_id == user_id)
            )
            return found is not None

    async def region_for(self, lat: float, lon: float) -> str | None:
        point = cast(func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326), Geography)
        async with self._sessions() as session:
            code: str | None = await session.scalar(
                select(CoverageAreaModel.code)
                .where(CoverageAreaModel.active, func.ST_Covers(CoverageAreaModel.area, point))
                .order_by(CoverageAreaModel.code)
                .limit(1)
            )
            return code

    async def emergency_default(self, region_code: str, language: str) -> dict[str, Any] | None:
        async with self._sessions() as session:
            row = await session.get(EmergencyDefaultModel, (region_code, language))
            return dict(row.instructions) if row is not None else None

    # ------------------------------------------------------------------ create

    async def _create(
        self, session: AsyncSession, new: NewRecommendation
    ) -> tuple[ConversationModel, RecommendationModel, TravelRequestModel]:
        request = new.request
        now = new.now
        if new.conversation_id is None:
            conversation = ConversationModel(
                id=new_id(),
                user_id=new.user_id,
                title=_title(request),
                language=request.language,
                message_count=0,
                created_at=now,
                updated_at=now,
                expires_at=expires_at(now, new.conversation_days),
            )
            session.add(conversation)
            await session.flush()
        else:
            found = await session.scalar(
                select(ConversationModel)
                .where(
                    ConversationModel.id == new.conversation_id,
                    ConversationModel.user_id == new.user_id,
                )
                .with_for_update()
            )
            if found is None:
                raise LookupError("conversation not found")
            conversation = found

        expiry = expires_at(now, new.retention_days)
        travel = TravelRequestModel(
            id=new_id(),
            user_id=new.user_id,
            conversation_id=conversation.id,
            trip_id=new.trip_id,
            source=new.source.value,
            origin=point_value(request.origin),
            origin_name=request.origin.name,
            destination=point_value(request.destination),
            destination_name=request.destination.name,
            waypoints=[point_json(p) for p in request.waypoints],
            departure_time=request.departure_time,
            timezone=request.timezone,
            language=request.language,
            preferences=preferences_json(request.preferences),
            has_question=request.question is not None,
            mode=new.mode.value,
            cache_key=new.cache_key,
            correlation_id=new.correlation_id,
            created_at=now,
            expires_at=expiry,
        )
        session.add(travel)
        await session.flush()
        recommendation = RecommendationModel(
            id=new_id(),
            request_id=travel.id,
            user_id=new.user_id,
            conversation_id=conversation.id,
            trip_id=new.trip_id,
            status=RecommendationStatus.PROCESSING.value,
            origin_name=request.origin.name,
            destination_name=request.destination.name,
            departure_time=request.departure_time,
            created_at=now,
            expires_at=expiry,
        )
        session.add(recommendation)
        await session.flush()
        if request.question is not None:
            session.add(
                MessageModel(
                    id=new_id(),
                    conversation_id=conversation.id,
                    role=MessageRole.USER.value,
                    content=request.question,
                    recommendation_id=recommendation.id,
                    created_at=now,
                )
            )
            conversation.message_count += 1
        conversation.last_request_id = travel.id
        conversation.updated_at = now
        conversation.expires_at = expires_at(now, new.conversation_days)
        return conversation, recommendation, travel

    async def create_pending(self, new: NewRecommendation) -> CreatedRecommendation:
        async with self._sessions() as session, session.begin():
            conversation, recommendation, travel = await self._create(session, new)
            job = JobModel(
                id=new.job_id or new_id(),
                user_id=new.user_id,
                type=job_type_for(new.source).value,
                recommendation_id=recommendation.id,
                status=JobStatus.QUEUED.value,
                stage=JobStage.QUEUED.value,
                progress=0,
                attempts=0,
                created_at=new.now,
                expires_at=expires_at(new.now, new.retention_days),
            )
            session.add(job)
            return CreatedRecommendation(
                travel.id, recommendation.id, conversation.id, job.id, new.now
            )

    async def create_completed(
        self, new: NewRecommendation, result: StoredResult
    ) -> CreatedRecommendation:
        async with self._sessions() as session, session.begin():
            conversation, recommendation, travel = await self._create(session, new)
            store_message = await _link_trip(session, recommendation, travel, result)
            _apply_result(
                session, conversation, recommendation, result, new.now, store_message=store_message
            )
            conversation.expires_at = expires_at(new.now, new.conversation_days)
            return CreatedRecommendation(
                travel.id, recommendation.id, conversation.id, None, new.now
            )

    async def set_task_id(self, job_id: UUID, task_id: str) -> None:
        async with self._sessions() as session, session.begin():
            job = await session.get(JobModel, job_id)
            if job is not None:
                job.celery_task_id = task_id[:64]

    async def fail_job(self, job_id: UUID, error_code: str, now: datetime) -> None:
        async with self._sessions() as session, session.begin():
            job = await session.get(JobModel, job_id, with_for_update=True)
            if job is None:
                return
            _mark_failed(job, error_code, now)
            recommendation = await session.get(RecommendationModel, job.recommendation_id)
            if recommendation is not None:
                _fail_recommendation(recommendation, error_code, now)

    # ------------------------------------------------------------------ reads

    async def get_recommendation(
        self, user_id: UUID, recommendation_id: UUID
    ) -> RecommendationRecord | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(RecommendationModel).where(
                    RecommendationModel.id == recommendation_id,
                    RecommendationModel.user_id == user_id,
                )
            )
            if row is None:
                return None
            job_id = await session.scalar(
                select(JobModel.id)
                .where(JobModel.recommendation_id == row.id, JobModel.status.in_(_ACTIVE))
                .order_by(JobModel.created_at.desc())
                .limit(1)
            )
            return RecommendationRecord(
                id=row.id,
                user_id=row.user_id,
                request_id=row.request_id,
                conversation_id=row.conversation_id,
                status=RecommendationStatus(row.status),
                payload=row.payload,
                error_code=row.error_code,
                created_at=row.created_at,
                job_id=job_id,
            )

    async def feedback_target(
        self, user_id: UUID, recommendation_id: UUID
    ) -> RecommendationStatus | None:
        async with self._sessions() as session:
            status = await session.scalar(
                select(RecommendationModel.status).where(
                    RecommendationModel.id == recommendation_id,
                    RecommendationModel.user_id == user_id,
                )
            )
            return RecommendationStatus(status) if status is not None else None

    async def get_job(self, user_id: UUID, job_id: UUID) -> JobRecord | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(JobModel).where(JobModel.id == job_id, JobModel.user_id == user_id)
            )
            return _job_record(row) if row is not None else None

    async def list_recommendations(
        self,
        user_id: UUID,
        *,
        limit: int,
        cursor: Cursor | None,
        created_from: datetime | None,
        created_to: datetime | None,
        risk_level: RiskLevel | None,
    ) -> list[RecommendationSummaryRecord]:
        model = RecommendationModel
        query = select(model).where(model.user_id == user_id)
        if cursor is not None:
            query = query.where(tuple_(model.created_at, model.id) < (cursor.at, cursor.id))
        if created_from is not None:
            query = query.where(model.created_at >= created_from)
        if created_to is not None:
            query = query.where(model.created_at < created_to)
        if risk_level is not None:
            query = query.where(model.risk_level == risk_level.value)
        query = query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
        return [summary_record(row) for row in rows]

    # ------------------------------------------------------------------ worker

    async def start_job(
        self, job_id: UUID, now: datetime, *, context_messages: int
    ) -> WorkItem | None:
        async with self._sessions() as session, session.begin():
            job = await session.get(JobModel, job_id, with_for_update=True)
            if job is None or job.status not in _ACTIVE or job.recommendation_id is None:
                return None
            job.status = JobStatus.RUNNING.value
            job.started_at = job.started_at or now
            job.attempts += 1

            recommendation = await session.get(RecommendationModel, job.recommendation_id)
            user = await session.get(UserModel, job.user_id)
            assert recommendation is not None
            assert user is not None
            question = await session.scalar(
                select(MessageModel.content).where(
                    MessageModel.recommendation_id == recommendation.id,
                    MessageModel.role == MessageRole.USER.value,
                )
            )
            request, travel = await load_request(
                session, recommendation.request_id, question=question
            )
            context: tuple[tuple[str, str], ...] = ()
            previous: UUID | None = None
            if recommendation.conversation_id is not None:
                context = await self._context(
                    session, recommendation.conversation_id, recommendation.id, context_messages
                )
                conversation = await session.get(ConversationModel, recommendation.conversation_id)
                if conversation is not None and conversation.last_recommendation_id not in (
                    None,
                    recommendation.id,
                ):
                    previous = conversation.last_recommendation_id
            return WorkItem(
                job_id=job.id,
                attempt=job.attempts,
                user=user_ref(user),
                recommendation_id=recommendation.id,
                request_id=recommendation.request_id,
                conversation_id=recommendation.conversation_id,
                previous_recommendation_id=previous,
                request=request,
                context=context,
                cache_key=travel.cache_key,
                analytics=user.consent_analytics,
            )

    async def _context(
        self, session: AsyncSession, conversation_id: UUID, current: UUID, limit: int
    ) -> tuple[tuple[str, str], ...]:
        if limit <= 0:
            return ()
        rows = (
            await session.execute(
                select(MessageModel.role, MessageModel.content)
                .where(
                    MessageModel.conversation_id == conversation_id,
                    or_(
                        MessageModel.recommendation_id.is_(None),
                        MessageModel.recommendation_id != current,
                    ),
                )
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(limit)
            )
        ).all()
        return tuple((role, content) for role, content in reversed(rows))

    async def job_cancelled(self, job_id: UUID) -> bool:
        """True once the job is no longer queued or running (cancelled, reaped or gone)."""
        async with self._sessions() as session:
            status = await session.scalar(select(JobModel.status).where(JobModel.id == job_id))
            return status not in _ACTIVE

    async def cancel_job(
        self, user_id: UUID, job_id: UUID, *, now: datetime
    ) -> tuple[CancelOutcome, JobRecord | None]:
        async with self._sessions() as session, session.begin():
            job = await session.scalar(
                select(JobModel)
                .where(JobModel.id == job_id, JobModel.user_id == user_id)
                .with_for_update()
            )
            if job is None:
                return None, None
            if job.status not in _ACTIVE:
                return "not_cancellable", _job_record(job)
            job.status = JobStatus.CANCELLED.value
            job.stage = JobStage.CANCELLED.value
            job.cancel_requested_at = now
            job.finished_at = now
            if job.recommendation_id is not None:
                recommendation = await session.get(RecommendationModel, job.recommendation_id)
                if recommendation is not None:
                    recommendation.status = RecommendationStatus.CANCELLED.value
                    recommendation.completed_at = now
            return "cancelled", _job_record(job)

    async def reap_stuck_jobs(
        self, *, older_than: datetime, now: datetime, limit: int
    ) -> list[JobRecord]:
        async with self._sessions() as session, session.begin():
            jobs = (
                await session.scalars(
                    select(JobModel)
                    .where(JobModel.status.in_(_ACTIVE), JobModel.created_at < older_than)
                    .order_by(JobModel.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            reaped = []
            for job in jobs:
                _mark_failed(job, _STUCK_CODE, now)
                if job.recommendation_id is not None:
                    recommendation = await session.get(RecommendationModel, job.recommendation_id)
                    if recommendation is not None:
                        _fail_recommendation(recommendation, _STUCK_CODE, now)
                reaped.append(_job_record(job))
            return reaped

    async def finish_job(self, job_id: UUID, outcome: JobOutcome) -> bool:
        """Store the outcome; False when the job was cancelled or reaped meanwhile (D-73)."""
        now = outcome.finished_at
        async with self._sessions() as session, session.begin():
            job = await session.get(JobModel, job_id, with_for_update=True)
            if job is None:
                return False
            applied = job.status in _ACTIVE
            recommendation = await session.get(RecommendationModel, job.recommendation_id)
            assert recommendation is not None
            if not applied:
                if outcome.status is not JobStatus.CANCELLED:
                    log.info("job_result_discarded", job_id=str(job_id), status=job.status)
            elif outcome.status is JobStatus.SUCCEEDED and outcome.result is not None:
                job.status = JobStatus.SUCCEEDED.value
                job.stage = JobStage.COMPLETED.value
                job.progress = 100
                job.finished_at = now
                conversation = None
                if recommendation.conversation_id is not None:
                    conversation = await session.get(
                        ConversationModel, recommendation.conversation_id
                    )
                travel = await session.get(TravelRequestModel, recommendation.request_id)
                assert travel is not None
                store_message = await _link_trip(session, recommendation, travel, outcome.result)
                _apply_result(
                    session,
                    conversation,
                    recommendation,
                    outcome.result,
                    now,
                    store_message=store_message,
                )
                if conversation is not None:
                    conversation.expires_at = expires_at(now, outcome.conversation_days)
                if outcome.prediction is not None:
                    await _store_prediction(session, job.user_id, recommendation.id, outcome)
            elif outcome.status is JobStatus.CANCELLED:
                job.status = JobStatus.CANCELLED.value
                job.stage = JobStage.CANCELLED.value
                job.finished_at = now
                recommendation.status = RecommendationStatus.CANCELLED.value
                recommendation.completed_at = now
            else:
                code = outcome.error_code or "INTERNAL_ERROR"
                _mark_failed(job, code, now)
                _fail_recommendation(recommendation, code, now)
            if outcome.agent_run is not None:
                run = outcome.agent_run
                session.add(
                    AgentRunModel(
                        id=run.run_id,
                        job_id=job.id,
                        attempt=run.attempt,
                        status=run.status.value,
                        http_status=run.http_status,
                        error_code=run.error_code[:40] if run.error_code else None,
                        duration_ms=int((run.finished_at - run.started_at).total_seconds() * 1000),
                        tool_calls=run.tool_calls,
                        agent_version=run.agent_version,
                        trace_id=run.trace_id[:64] if run.trace_id else None,
                        started_at=run.started_at,
                        finished_at=run.finished_at,
                    )
                )
            return applied


async def _store_prediction(
    session: AsyncSession, user_id: UUID, recommendation_id: UUID, outcome: JobOutcome
) -> None:
    """Anonymized copy for MLOps, only with the user's analytics consent (D-13, D-75)."""
    prediction = outcome.prediction
    assert prediction is not None
    consent = await session.scalar(
        select(UserModel.consent_analytics).where(UserModel.id == user_id)
    )
    if not consent:
        return
    now = outcome.finished_at
    session.add(
        PredictionRecordModel(
            id=new_id(),
            recommendation_id=recommendation_id,
            origin_geohash=prediction.origin_geohash,
            destination_geohash=prediction.destination_geohash,
            region_code=prediction.region_code,
            departure_bucket=prediction.departure_bucket,
            lead_time_hours=prediction.lead_time_hours,
            travel_modes=list(prediction.travel_modes),
            status=prediction.status.value,
            risk_level=prediction.risk_level.value if prediction.risk_level else None,
            risk_score=_decimal(prediction.risk_score),
            risk_confidence=_decimal(prediction.risk_confidence),
            recommendation_type=(
                prediction.recommendation_type.value if prediction.recommendation_type else None
            ),
            hazard_types=list(prediction.hazard_types),
            data_freshness=prediction.data_freshness,
            service_status=prediction.service_status,
            safety_gate_rules=list(prediction.safety_gate_rules),
            agent_version=prediction.agent_version,
            risk_model_version=prediction.risk_model_version,
            prompt_version=prediction.prompt_version,
            created_at=now,
            expires_at=expires_at(now, outcome.prediction_days),
        )
    )


def _coordinates(points: list[dict[str, Any]]) -> list[tuple[float, float]]:
    return [(p["lat"], p["lon"]) for p in points]


async def _same_route(session: AsyncSession, trip: TripModel, travel: TravelRequestModel) -> bool:
    """Whether the request still describes the trip as it is now (D-64)."""
    if (
        trip.departure_time != travel.departure_time
        or _coordinates(trip.waypoints) != _coordinates(travel.waypoints)
        or trip.preferences != travel.preferences
    ):
        return False
    same = await session.scalar(
        select(
            and_(
                func.ST_Equals(
                    cast(TripModel.origin, Geometry), cast(TravelRequestModel.origin, Geometry)
                ),
                func.ST_Equals(
                    cast(TripModel.destination, Geometry),
                    cast(TravelRequestModel.destination, Geometry),
                ),
            )
        )
        .select_from(TripModel)
        .join(TravelRequestModel, TravelRequestModel.id == travel.id)
        .where(TripModel.id == trip.id)
    )
    return bool(same)


async def _link_trip(
    session: AsyncSession,
    recommendation: RecommendationModel,
    travel: TravelRequestModel,
    result: StoredResult,
) -> bool:
    """Point the trip at a finished assessment; returns whether to store the assistant message.

    A scheduled re-assessment (TRIP_ALERT) only speaks when the risk changed (D-66).
    """
    alert = travel.source == RequestSource.TRIP_ALERT.value
    if recommendation.trip_id is None:
        return not alert
    trip = await session.get(TripModel, recommendation.trip_id, with_for_update=True)
    if trip is None:
        return not alert
    previous = None
    if trip.last_recommendation_id is not None:
        previous = await session.get(RecommendationModel, trip.last_recommendation_id)
    if previous is not None and previous.created_at > recommendation.created_at:
        return not alert
    trip.last_recommendation_id = recommendation.id
    if await _same_route(session, trip, travel):
        trip.assessment_outdated = False
    if not alert or previous is None:
        return not alert
    level = result.risk_level.value if result.risk_level else None
    action = result.recommendation_type.value if result.recommendation_type else None
    changed = (previous.risk_level, previous.recommendation_type) != (level, action)
    if changed:
        log.info(
            "trip_alert_raised",
            trip_id=str(trip.id),
            previous_risk_level=previous.risk_level,
            risk_level=level,
        )
    return changed


def _apply_result(
    session: AsyncSession,
    conversation: ConversationModel | None,
    recommendation: RecommendationModel,
    result: StoredResult,
    now: datetime,
    *,
    store_message: bool = True,
) -> None:
    recommendation.status = result.status.value
    recommendation.risk_level = result.risk_level.value if result.risk_level else None
    recommendation.risk_score = _decimal(result.risk_score)
    recommendation.risk_confidence = _decimal(result.risk_confidence)
    recommendation.recommendation_type = (
        result.recommendation_type.value if result.recommendation_type else None
    )
    recommendation.payload = result.payload
    recommendation.warning_codes = list(result.warning_codes)
    recommendation.safety_gate_rules = list(result.applied_rules)
    recommendation.overall_is_stale = result.overall_is_stale
    recommendation.valid_until = result.valid_until
    recommendation.api_version = result.api_version
    recommendation.agent_version = result.agent_version
    recommendation.risk_model_version = result.risk_model_version
    recommendation.prompt_version = result.prompt_version
    recommendation.completed_at = now
    if conversation is None:
        return
    if result.message and store_message:
        session.add(
            MessageModel(
                id=new_id(),
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT.value,
                content=truncate(result.message, MESSAGE_MAX_CHARS),
                recommendation_id=recommendation.id,
                created_at=now,
            )
        )
        conversation.message_count += 1
    conversation.last_recommendation_id = recommendation.id
    conversation.updated_at = now


def _mark_failed(job: JobModel, error_code: str, now: datetime) -> None:
    job.status = JobStatus.FAILED.value
    job.stage = JobStage.FAILED.value
    job.error_code = error_code[:40]
    job.finished_at = now


def _fail_recommendation(
    recommendation: RecommendationModel, error_code: str, now: datetime
) -> None:
    recommendation.status = RecommendationStatus.FAILED.value
    recommendation.error_code = error_code[:40]
    recommendation.completed_at = now
