"""Fake application services for HTTP-layer tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.errors import AppError, ErrorCode
from app.core.ids import new_id
from app.domain.enums import (
    FeedbackOutcome,
    JobStage,
    JobStatus,
    JobType,
    MessageRole,
    RecommendationStatus,
    RecommendationType,
    ReportType,
    ReviewStatus,
    RiskLevel,
)
from app.domain.errors import DomainError
from app.domain.normalization import GeoPoint, NormalizationLimits
from app.domain.profile import (
    Consents,
    Profile,
    ProfileChanges,
    apply_profile_changes,
    mask_email,
)
from app.domain.trips import TripChanges, TripDraft, apply_trip_changes
from app.infrastructure.redis.job_state import JobEvent
from app.services.conversation_service import MessageReply
from app.services.pagination import Page
from app.services.ports import (
    ConversationRecord,
    FeedbackRecord,
    JobRecord,
    MessageRecord,
    ProfileRecord,
    RecommendationRecord,
    RecommendationSummaryRecord,
    ReviewItem,
    TripRecord,
    UserRef,
)
from app.services.recommendation_service import Accepted, CreateOutcome, CreateRecommendation

T0 = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
USER = UserRef(new_id(), "pseudo", "th", None)


def payload(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "status": "completed",
        "valid_until": "2026-09-17T08:08:00Z",
        "language": "en",
        "risk": {"level": "LOW", "score": 0.12, "confidence": 0.9, "factors": []},
        "recommendation": {
            "type": "TRAVEL_NORMALLY",
            "summary": "Conditions are safe for your trip.",
            "reasons": ["No active warnings on the route."],
            "suggested_departure_time": None,
        },
        "routes": {
            "primary": {
                "route_id": "r-primary",
                "label": "Train",
                "travel_modes": ["TRAIN"],
                "distance_km": 661.0,
                "duration_minutes": 690.0,
                "risk_level": "LOW",
                "geometry": {"type": "LineString", "coordinates": [[100.5, 13.7], [98.9, 18.7]]},
                "legs": [
                    {
                        "mode": "TRAIN",
                        "from": "Krung Thep Aphiwat",
                        "to": "Chiang Mai",
                        "departure_at": None,
                        "arrival_at": None,
                        "operator": "SRT",
                        "service_status": "on_time",
                    }
                ],
                "restrictions": [],
                "tips": [],
            },
            "alternatives": [],
        },
        "hazards": [],
        "emergency_instructions": None,
        "sources": [
            {
                "source_id": "src-weather",
                "name": "TMD",
                "category": "WEATHER",
                "url": "https://www.tmd.go.th",
                "retrieved_at": "2026-09-17T07:59:00Z",
            }
        ],
        "data_freshness": {
            "overall_is_stale": False,
            "items": [
                {
                    "category": "WEATHER",
                    "updated_at": "2026-09-17T07:40:00Z",
                    "age_seconds": 1200,
                    "is_stale": False,
                }
            ],
        },
        "service_status": {"weather": "ok", "disaster": "ok"},
        "clarification": None,
        "warnings": [],
        "versions": {"api": "1.0.0", "agent": "a", "risk_model": "r", "prompt": "p"},
        "disclaimer": "Follow official announcements.",
    }
    body.update(changes)
    return body


def record(
    status: RecommendationStatus = RecommendationStatus.COMPLETED, **changes: Any
) -> RecommendationRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": USER.id,
        "request_id": new_id(),
        "conversation_id": new_id(),
        "status": status,
        "payload": payload() if status is not RecommendationStatus.PROCESSING else None,
        "error_code": None,
        "created_at": T0,
        "job_id": None,
    }
    values.update(changes)
    return RecommendationRecord(**values)


def job(**changes: Any) -> JobRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": USER.id,
        "type": JobType.RECOMMENDATION,
        "status": JobStatus.RUNNING,
        "stage": JobStage.ASSESSING_RISK,
        "progress": 60,
        "recommendation_id": new_id(),
        "error_code": None,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(changes)
    return JobRecord(**values)


@dataclass
class FakeRecommendations:
    outcome: CreateOutcome | Exception | None = None
    records: dict[UUID, RecommendationRecord] = field(default_factory=dict)
    commands: list[CreateRecommendation] = field(default_factory=list)
    page: Page[RecommendationSummaryRecord] = field(default_factory=lambda: Page([], None))
    list_calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, user: UserRef, command: CreateRecommendation) -> CreateOutcome:
        self.commands.append(command)
        if isinstance(self.outcome, AppError | DomainError):
            raise self.outcome
        assert self.outcome is not None
        assert not isinstance(self.outcome, Exception)
        return self.outcome

    async def list(self, user: UserRef, **filters: Any) -> Page[RecommendationSummaryRecord]:
        self.list_calls.append(filters)
        return self.page

    async def get(self, user: UserRef, recommendation_id: UUID) -> RecommendationRecord:
        found = self.records.get(recommendation_id)
        if found is None or found.user_id != user.id:
            raise AppError(ErrorCode.NOT_FOUND)
        return found


@dataclass
class FakeJobs:
    jobs: dict[UUID, JobRecord] = field(default_factory=dict)
    events: list[JobEvent | None] = field(default_factory=list)
    tickets: dict[str, tuple[UUID, UUID]] = field(default_factory=dict)
    closed: list[str] = field(default_factory=list)
    last_event_ids: list[str | None] = field(default_factory=list)
    hang: bool = False

    async def get(self, user_id: UUID, job_id: UUID) -> JobRecord:
        found = self.jobs.get(job_id)
        if found is None or found.user_id != user_id:
            raise AppError(ErrorCode.NOT_FOUND)
        return found

    async def issue_ticket(self, user_id: UUID, job_id: UUID) -> tuple[str, int]:
        await self.get(user_id, job_id)
        ticket = f"ticket-{len(self.tickets)}"
        self.tickets[ticket] = (user_id, job_id)
        return ticket, 60

    async def redeem_ticket(self, ticket: str, job_id: UUID) -> UUID:
        found = self.tickets.pop(ticket, None)
        if found is None or found[1] != job_id:
            raise AppError(ErrorCode.UNAUTHENTICATED)
        return found[0]

    async def cancel(self, user_id: UUID, job_id: UUID) -> JobRecord:
        found = await self.get(user_id, job_id)
        if found.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise AppError(ErrorCode.JOB_NOT_CANCELLABLE)
        cancelled = replace(found, status=JobStatus.CANCELLED, stage=JobStage.CANCELLED)
        self.jobs[job_id] = cancelled
        return cancelled

    async def open_stream(self, user_id: UUID, job_id: UUID) -> tuple[JobRecord, str]:
        return await self.get(user_id, job_id), "conn-1"

    async def close_stream(self, user_id: UUID, connection_id: str) -> None:
        await asyncio.sleep(0)  # a real await point, like the Redis call
        self.closed.append(connection_id)

    async def stream(
        self,
        user_id: UUID,
        job: JobRecord,
        connection_id: str,
        *,
        last_event_id: str | None,
        disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[JobEvent | None]:
        self.last_event_ids.append(last_event_id)
        for event in self.events:
            yield event
        if self.hang:
            await asyncio.Event().wait()


class FakeUsers:
    async def resolve(self, principal: object) -> UserRef:
        return USER


def conversation(**changes: Any) -> ConversationRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": USER.id,
        "title": "Trip north",
        "language": "th",
        "created_at": T0,
        "updated_at": T0,
        "last_recommendation_id": None,
        "message_count": 0,
    }
    values.update(changes)
    return ConversationRecord(**values)


def message(**changes: Any) -> MessageRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "conversation_id": new_id(),
        "role": MessageRole.ASSISTANT,
        "content": "Take the train.",
        "recommendation_id": new_id(),
        "created_at": T0,
    }
    values.update(changes)
    return MessageRecord(**values)


def summary(**changes: Any) -> RecommendationSummaryRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "created_at": T0,
        "status": RecommendationStatus.COMPLETED,
        "risk_level": RiskLevel.LOW,
        "recommendation_type": RecommendationType.TRAVEL_NORMALLY,
        "origin_name": "Bangkok",
        "destination_name": "Chiang Mai",
        "departure_time": T0,
    }
    values.update(changes)
    return RecommendationSummaryRecord(**values)


@dataclass
class FakeConversations:
    records: dict[UUID, ConversationRecord] = field(default_factory=dict)
    message_page: Page[MessageRecord] = field(default_factory=lambda: Page([], None))
    reply: MessageReply | Accepted | Exception | None = None
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def _owned(self, user: UserRef, conversation_id: UUID) -> ConversationRecord:
        found = self.records.get(conversation_id)
        if found is None or found.user_id != user.id:
            raise AppError(ErrorCode.NOT_FOUND)
        return found

    async def create(
        self, user: UserRef, *, title: str | None, language: str | None, accept_language: str | None
    ) -> ConversationRecord:
        self.calls.append(
            ("create", {"title": title, "language": language, "accept_language": accept_language})
        )
        created = conversation(title=title, language=language or "th")
        self.records[created.id] = created
        return created

    async def get(self, user: UserRef, conversation_id: UUID) -> ConversationRecord:
        return self._owned(user, conversation_id)

    async def list(
        self, user: UserRef, *, limit: int | None, cursor: str | None
    ) -> Page[ConversationRecord]:
        self.calls.append(("list", {"limit": limit, "cursor": cursor}))
        return Page(list(self.records.values()), "next-page")

    async def delete(self, user: UserRef, conversation_id: UUID) -> None:
        self._owned(user, conversation_id)
        del self.records[conversation_id]

    async def messages(
        self, user: UserRef, conversation_id: UUID, *, limit: int | None, cursor: str | None
    ) -> Page[MessageRecord]:
        self._owned(user, conversation_id)
        self.calls.append(("messages", {"limit": limit, "cursor": cursor}))
        return self.message_page

    async def post_message(
        self, user: UserRef, conversation_id: UUID, **kwargs: Any
    ) -> MessageReply | Accepted:
        self._owned(user, conversation_id)
        self.calls.append(("post_message", kwargs))
        if isinstance(self.reply, Exception):
            raise self.reply
        assert self.reply is not None
        return self.reply


def trip(**changes: Any) -> TripRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "user_id": USER.id,
        "draft": TripDraft(
            name="North trip",
            origin=GeoPoint(13.7563, 100.5018, name="Bangkok"),
            destination=GeoPoint(18.7883, 98.9853, name="Chiang Mai"),
            departure_time=T0 + timedelta(days=3),
            timezone="Asia/Bangkok",
        ),
        "last_assessment": None,
        "assessment_outdated": False,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(changes)
    return TripRecord(**values)


@dataclass
class FakeTrips:
    records: dict[UUID, TripRecord] = field(default_factory=dict)
    outcome: CreateOutcome | None = None
    page: Page[RecommendationSummaryRecord] = field(default_factory=lambda: Page([], None))
    calls: list[tuple[str, Any]] = field(default_factory=list)

    def _owned(self, user: UserRef, trip_id: UUID) -> TripRecord:
        found = self.records.get(trip_id)
        if found is None or found.user_id != user.id:
            raise AppError(ErrorCode.NOT_FOUND)
        return found

    async def create(self, user: UserRef, draft: TripDraft) -> TripRecord:
        self.calls.append(("create", draft))
        created = trip(draft=draft)
        self.records[created.id] = created
        return created

    async def get(self, user: UserRef, trip_id: UUID) -> TripRecord:
        return self._owned(user, trip_id)

    async def list(self, user: UserRef, **kwargs: Any) -> Page[TripRecord]:
        self.calls.append(("list", kwargs))
        return Page(list(self.records.values()), "next-page")

    async def update(self, user: UserRef, trip_id: UUID, changes: TripChanges) -> TripRecord:
        current = self._owned(user, trip_id)
        self.calls.append(("update", changes))
        draft = apply_trip_changes(
            current.draft, changes, now=T0, limits=NormalizationLimits(max_days_ahead=90)
        )
        updated = replace(current, draft=draft)
        self.records[trip_id] = updated
        return updated

    async def delete(self, user: UserRef, trip_id: UUID) -> None:
        self._owned(user, trip_id)
        del self.records[trip_id]

    async def assess(self, user: UserRef, trip_id: UUID, **kwargs: Any) -> CreateOutcome:
        self._owned(user, trip_id)
        self.calls.append(("assess", kwargs))
        assert self.outcome is not None
        return self.outcome

    async def assessments(
        self, user: UserRef, trip_id: UUID, **kwargs: Any
    ) -> Page[RecommendationSummaryRecord]:
        self._owned(user, trip_id)
        self.calls.append(("assessments", kwargs))
        return self.page


def feedback_record(**changes: Any) -> FeedbackRecord:
    values: dict[str, Any] = {
        "id": new_id(),
        "recommendation_id": new_id(),
        "rating": 1,
        "helpful": False,
        "outcome": FeedbackOutcome.UNKNOWN,
        "report_type": ReportType.UNSAFE_ADVICE,
        "comment": "Flooded road",
        "review_status": ReviewStatus.PENDING,
        "reviewed_at": None,
        "review_note": None,
        "created_at": T0,
    }
    values.update(changes)
    return FeedbackRecord(**values)


@dataclass
class FakeFeedback:
    records: dict[UUID, FeedbackRecord] = field(default_factory=dict)
    owned: set[UUID] = field(default_factory=set)
    calls: list[tuple[str, Any, dict[str, Any]]] = field(default_factory=list)

    async def submit(
        self, user: UserRef, recommendation_id: UUID, raw: Any, **kwargs: Any
    ) -> FeedbackRecord:
        if recommendation_id not in self.owned:
            raise AppError(ErrorCode.NOT_FOUND)
        self.calls.append(("submit", raw, kwargs))
        made = feedback_record(recommendation_id=recommendation_id)
        self.records[made.id] = made
        return made

    async def reviews(self, reviewer: str, **kwargs: Any) -> Page[ReviewItem]:
        self.calls.append(("reviews", reviewer, kwargs))
        items = [
            ReviewItem(r, {"recommendation": {"summary": "Go"}}) for r in self.records.values()
        ]
        return Page(items, "next-page")

    async def review(self, reviewer: str, feedback_id: UUID, **kwargs: Any) -> FeedbackRecord:
        self.calls.append(("review", reviewer, kwargs))
        found = self.records.get(feedback_id)
        if found is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if found.review_status is not ReviewStatus.PENDING:
            raise AppError(ErrorCode.REVIEW_NOT_PENDING)
        updated = replace(
            found,
            review_status=ReviewStatus(kwargs["decision"].value),
            review_note=kwargs["note"],
            reviewed_at=T0,
        )
        self.records[feedback_id] = updated
        return updated


def profile_record(**changes: Any) -> ProfileRecord:
    values: dict[str, Any] = {
        "user_id": USER.id,
        "profile": Profile(
            display_name="Sakda",
            language="th",
            timezone="Asia/Bangkok",
            home_region="TH",
            consents=Consents(True, T0, False, None),
        ),
        "created_at": T0,
    }
    values.update(changes)
    return ProfileRecord(**values)


@dataclass
class FakeMe:
    record: ProfileRecord = field(default_factory=profile_record)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def get(self, user: UserRef, *, email: str | None) -> tuple[ProfileRecord, str | None]:
        self.calls.append(("get", {"email": email}))
        return self.record, mask_email(email)

    async def update(self, user: UserRef, changes: ProfileChanges, **kwargs: Any) -> ProfileRecord:
        self.calls.append(("update", {"changes": changes, **kwargs}))
        profile = apply_profile_changes(self.record.profile, changes, now=T0)
        self.record = replace(self.record, profile=profile)
        return self.record

    async def delete(self, user: UserRef, **kwargs: Any) -> None:
        self.calls.append(("delete", kwargs))
