"""What the application services need from the outside world.

Services depend on these Protocols and records only; infrastructure implements them
(docs/04_project_structure.md section 2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

from app.domain.admin import AuditFilter, TimeRange
from app.domain.enums import (
    ActorType,
    AgentRunStatus,
    AuditResult,
    ExportStatus,
    FeedbackOutcome,
    JobStage,
    JobStatus,
    JobType,
    MessageRole,
    RecommendationStatus,
    RecommendationType,
    ReportType,
    RequestMode,
    RequestSource,
    ReviewStatus,
    RiskLevel,
    ServiceState,
    TripStatus,
)
from app.domain.feedback import FeedbackInput, ReviewDecision
from app.domain.normalization import NormalizedTravelRequest
from app.domain.prediction import PredictionData
from app.domain.profile import Profile
from app.domain.trips import TripDraft
from app.infrastructure.agent.client import AgentCallResult
from app.infrastructure.agent.contracts import AgentRunRequest, AgentVersions, ProgressLine
from app.infrastructure.redis.job_state import JobEvent, JobSnapshot
from app.services.pagination import Cursor
from app.services.recommendation_payload import Assessment, fallback_reply

# ------------------------------------------------------------------ records


@dataclass(frozen=True, slots=True)
class UserRef:
    id: UUID
    pseudonymous_id: str
    language: str
    home_region: str | None
    # Set once the user asked to delete the account (D-78).
    deletion_requested: bool = False


# None = no such job for this user.
CancelOutcome = Literal["cancelled", "not_cancellable"] | None


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    user_id: UUID
    profile: Profile
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NewRecommendation:
    user_id: UUID
    request: NormalizedTravelRequest
    mode: RequestMode
    source: RequestSource
    conversation_id: UUID | None
    trip_id: UUID | None
    cache_key: str | None
    correlation_id: str
    now: datetime
    retention_days: int
    conversation_days: int
    # Chosen by the caller so the active-job slot can be taken before the rows exist.
    job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreatedRecommendation:
    request_id: UUID
    recommendation_id: UUID
    conversation_id: UUID
    job_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StoredResult:
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_score: float | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    payload: dict[str, Any]
    warning_codes: tuple[str, ...]
    applied_rules: tuple[str, ...]
    overall_is_stale: bool
    valid_until: datetime | None
    api_version: str
    agent_version: str | None
    risk_model_version: str | None
    prompt_version: str | None
    # Stored as the assistant message of the conversation.
    message: str | None

    @classmethod
    def from_assessment(
        cls, assessment: Assessment, *, versions: AgentVersions, api_version: str
    ) -> StoredResult:
        clarification = assessment.payload.get("clarification") or {}
        return cls(
            status=assessment.status,
            risk_level=assessment.risk_level,
            risk_score=assessment.risk_score,
            risk_confidence=assessment.risk_confidence,
            recommendation_type=assessment.recommendation_type,
            payload=assessment.payload,
            warning_codes=assessment.warning_codes,
            applied_rules=assessment.applied_rules,
            overall_is_stale=assessment.overall_is_stale,
            valid_until=assessment.valid_until,
            api_version=api_version,
            agent_version=versions.agent,
            risk_model_version=versions.risk_model,
            prompt_version=versions.prompt,
            message=(
                assessment.summary
                or clarification.get("question")
                or fallback_reply(str(assessment.payload.get("language", "")))
            ),
        )


@dataclass(frozen=True, slots=True)
class RecommendationRecord:
    id: UUID
    user_id: UUID
    request_id: UUID
    conversation_id: UUID | None
    status: RecommendationStatus
    payload: dict[str, Any] | None
    error_code: str | None
    created_at: datetime
    job_id: UUID | None


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: UUID
    user_id: UUID
    type: JobType
    status: JobStatus
    stage: JobStage
    progress: int
    recommendation_id: UUID | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: JobSnapshot) -> JobRecord:
        return cls(
            id=snapshot.job_id,
            user_id=snapshot.user_id,
            type=snapshot.type,
            status=snapshot.status,
            stage=snapshot.stage,
            progress=snapshot.progress,
            recommendation_id=snapshot.recommendation_id,
            error_code=snapshot.error_code,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
        )


@dataclass(frozen=True, slots=True)
class RecommendationSummaryRecord:
    id: UUID
    created_at: datetime
    status: RecommendationStatus
    risk_level: RiskLevel | None
    recommendation_type: RecommendationType | None
    origin_name: str | None
    destination_name: str | None
    departure_time: datetime


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    id: UUID
    user_id: UUID
    title: str | None
    language: str
    created_at: datetime
    updated_at: datetime
    last_recommendation_id: UUID | None
    message_count: int


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    recommendation_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AssessmentSummary:
    recommendation_id: UUID
    status: RecommendationStatus
    risk_level: RiskLevel | None
    recommendation_type: RecommendationType | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TripRecord:
    id: UUID
    user_id: UUID
    draft: TripDraft
    last_assessment: AssessmentSummary | None
    assessment_outdated: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DueTrip:
    trip_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True)
class ExportRecord:
    id: UUID
    user_id: UUID
    status: ExportStatus
    object_key: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    id: UUID
    recommendation_id: UUID
    rating: int | None
    helpful: bool | None
    outcome: FeedbackOutcome
    report_type: ReportType | None
    comment: str | None
    review_status: ReviewStatus
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewItem:
    feedback: FeedbackRecord
    # The sanitized recommendation the report is about; None once it was deleted.
    recommendation: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    actor_type: ActorType
    actor_ref: str
    action: str
    target_type: str | None
    target_id: str | None
    result: AuditResult
    correlation_id: str
    ip_hash: str | None
    # Never personal data (docs/03_data_design.md section 3.12).
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkItem:
    job_id: UUID
    attempt: int
    user: UserRef
    recommendation_id: UUID
    request_id: UUID
    conversation_id: UUID | None
    previous_recommendation_id: UUID | None
    request: NormalizedTravelRequest
    # Earlier (role, content) pairs of the conversation, oldest first.
    context: tuple[tuple[str, str], ...]
    cache_key: str | None
    # The user agreed to analytics when the job started (checked again when storing).
    analytics: bool = False


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    run_id: UUID
    attempt: int
    status: AgentRunStatus
    http_status: int | None
    error_code: str | None
    started_at: datetime
    finished_at: datetime
    tool_calls: int | None
    agent_version: str | None
    trace_id: str | None


@dataclass(frozen=True, slots=True)
class JobOutcome:
    status: JobStatus
    finished_at: datetime
    result: StoredResult | None
    error_code: str | None
    agent_run: AgentRunRecord | None
    conversation_days: int
    # Stored only when the user agreed to analytics (D-13, D-75).
    prediction: PredictionData | None = None
    prediction_days: int = 365


# ------------------------------------------------------------------ ports


class RecommendationRepository(Protocol):
    async def get_or_create_user(
        self, issuer: str, subject: str, *, pseudonym: Callable[[UUID], str]
    ) -> UserRef: ...

    async def conversation_exists(self, user_id: UUID, conversation_id: UUID) -> bool: ...

    async def trip_exists(self, user_id: UUID, trip_id: UUID) -> bool: ...

    async def region_for(self, lat: float, lon: float) -> str | None: ...

    async def create_pending(self, new: NewRecommendation) -> CreatedRecommendation: ...

    async def create_completed(
        self, new: NewRecommendation, result: StoredResult
    ) -> CreatedRecommendation: ...

    async def set_task_id(self, job_id: UUID, task_id: str) -> None: ...

    async def fail_job(self, job_id: UUID, error_code: str, now: datetime) -> None: ...

    async def get_recommendation(
        self, user_id: UUID, recommendation_id: UUID
    ) -> RecommendationRecord | None: ...

    async def get_job(self, user_id: UUID, job_id: UUID) -> JobRecord | None: ...

    async def list_recommendations(
        self,
        user_id: UUID,
        *,
        limit: int,
        cursor: Cursor | None,
        created_from: datetime | None,
        created_to: datetime | None,
        risk_level: RiskLevel | None,
    ) -> list[RecommendationSummaryRecord]: ...

    async def start_job(
        self, job_id: UUID, now: datetime, *, context_messages: int
    ) -> WorkItem | None: ...

    async def emergency_default(self, region_code: str, language: str) -> dict[str, Any] | None: ...

    async def finish_job(self, job_id: UUID, outcome: JobOutcome) -> bool: ...

    async def job_cancelled(self, job_id: UUID) -> bool: ...

    async def cancel_job(
        self, user_id: UUID, job_id: UUID, *, now: datetime
    ) -> tuple[CancelOutcome, JobRecord | None]: ...

    async def reap_stuck_jobs(
        self, *, older_than: datetime, now: datetime, limit: int
    ) -> list[JobRecord]: ...

    async def feedback_target(
        self, user_id: UUID, recommendation_id: UUID
    ) -> RecommendationStatus | None: ...


class ConversationRepository(Protocol):
    """List methods return up to `limit + 1` rows (see pagination.build_page)."""

    async def create(
        self,
        user_id: UUID,
        *,
        title: str | None,
        language: str,
        now: datetime,
        retention_days: int,
    ) -> ConversationRecord: ...

    async def get(self, user_id: UUID, conversation_id: UUID) -> ConversationRecord | None: ...

    async def list_conversations(
        self, user_id: UUID, *, limit: int, cursor: Cursor | None
    ) -> list[ConversationRecord]: ...

    async def delete(self, user_id: UUID, conversation_id: UUID) -> bool: ...

    async def messages(
        self, user_id: UUID, conversation_id: UUID, *, limit: int, cursor: Cursor | None
    ) -> list[MessageRecord] | None: ...

    async def last_request(
        self, user_id: UUID, conversation_id: UUID
    ) -> NormalizedTravelRequest | None: ...

    async def reply_for(self, user_id: UUID, recommendation_id: UUID) -> MessageRecord | None: ...


class TripRepository(Protocol):
    """List methods return up to `limit + 1` rows (see pagination.build_page)."""

    async def create(
        self, user_id: UUID, draft: TripDraft, *, now: datetime, retention_days: int
    ) -> TripRecord: ...

    async def get(self, user_id: UUID, trip_id: UUID) -> TripRecord | None: ...

    async def list_trips(
        self, user_id: UUID, *, limit: int, cursor: Cursor | None, status: TripStatus | None
    ) -> list[TripRecord]: ...

    async def update(
        self,
        user_id: UUID,
        trip_id: UUID,
        draft: TripDraft,
        *,
        outdated: bool,
        now: datetime,
        retention_days: int,
    ) -> TripRecord | None: ...

    async def delete(self, user_id: UUID, trip_id: UUID) -> bool: ...

    async def assessments(
        self, user_id: UUID, trip_id: UUID, *, limit: int, cursor: Cursor | None
    ) -> list[RecommendationSummaryRecord] | None: ...

    async def conversation_for(self, user_id: UUID, trip_id: UUID) -> UUID | None: ...

    async def due_for_alerts(
        self,
        now: datetime,
        *,
        window: timedelta,
        stale_after: timedelta,
        processing_after: timedelta,
        limit: int,
    ) -> list[DueTrip]: ...

    async def user(self, user_id: UUID) -> UserRef | None: ...


class UserRepository(Protocol):
    async def profile(self, user_id: UUID) -> ProfileRecord | None: ...

    async def update_profile(
        self, user_id: UUID, profile: Profile, *, now: datetime
    ) -> ProfileRecord | None: ...

    async def request_deletion(self, user_id: UUID, *, now: datetime) -> bool: ...

    async def recent_job_ids(self, user_id: UUID, *, since: datetime) -> list[UUID]: ...

    async def delete_account(self, user_id: UUID) -> str | None: ...

    async def pending_deletions(self, *, older_than: datetime, limit: int) -> list[UUID]: ...


class FeedbackRepository(Protocol):
    """`reviews` returns up to `limit + 1` rows (see pagination.build_page)."""

    async def create(
        self,
        recommendation_id: UUID,
        pseudonymous_id: str,
        feedback: FeedbackInput,
        *,
        review_status: ReviewStatus,
        now: datetime,
        retention_days: int,
    ) -> FeedbackRecord: ...

    async def reviews(
        self, *, status: ReviewStatus, limit: int, cursor: Cursor | None
    ) -> list[ReviewItem]: ...

    async def review(
        self,
        feedback_id: UUID,
        *,
        decision: ReviewDecision,
        note: str | None,
        reviewer: str,
        now: datetime,
    ) -> FeedbackRecord | Literal["not_pending"] | None: ...


class ExportRepository(Protocol):
    async def create(self, user_id: UUID, *, now: datetime) -> ExportRecord: ...

    async def get(self, user_id: UUID, export_id: UUID) -> ExportRecord | None: ...

    async def start(self, export_id: UUID) -> UUID | None: ...

    async def collect(self, user_id: UUID) -> dict[str, Any]: ...

    async def finish(
        self, export_id: UUID, *, object_key: str, now: datetime, expires_at: datetime
    ) -> None: ...

    async def fail(self, export_id: UUID, *, now: datetime) -> None: ...

    async def object_keys(self, user_id: UUID) -> list[str]: ...

    async def fail_stuck(self, *, older_than: datetime, now: datetime) -> int: ...


class ObjectStorePort(Protocol):
    async def put(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def download_url(self, key: str, *, expires_seconds: int) -> str: ...


class ServiceReportPort(Protocol):
    """Where workers note the service states the Agent reported (E-23)."""

    async def record(
        self, states: Mapping[str, ServiceState], *, at: datetime, ttl_seconds: int
    ) -> None: ...


class CooldownPort(Protocol):
    async def claim(self, key: str, *, seconds: int) -> int | None:
        """None when claimed; otherwise the seconds left on the existing claim."""
        ...

    async def release(self, key: str) -> None: ...


class AuditPort(Protocol):
    async def write(self, entry: AuditEntry) -> None: ...


ProgressCallback = Callable[[ProgressLine], Awaitable[None]]


class AgentPort(Protocol):
    async def run(
        self,
        request: AgentRunRequest,
        *,
        deadline: datetime,
        on_progress: ProgressCallback | None = None,
    ) -> AgentCallResult: ...


class JobStatePort(Protocol):
    async def create(self, snapshot: JobSnapshot) -> None: ...

    async def update(
        self,
        job_id: UUID,
        *,
        updated_at: datetime,
        status: JobStatus | None = None,
        stage: JobStage | None = None,
        progress: int | None = None,
        error_code: str | None = None,
    ) -> None: ...

    async def publish(self, job_id: UUID, event: str, data: dict[str, Any]) -> str: ...

    async def get(self, job_id: UUID) -> JobSnapshot | None: ...

    async def read(self, job_id: UUID, *, after: str, block_ms: int | None) -> list[JobEvent]: ...


class TicketPort(Protocol):
    async def issue(self, user_id: UUID, job_id: UUID, *, ttl_seconds: int) -> str: ...

    async def redeem(self, ticket: str) -> tuple[UUID, UUID] | None: ...


class CachePort(Protocol):
    async def get(self, cache_key: str) -> dict[str, Any] | None: ...

    async def put(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: int) -> None: ...


class UserDataPort(Protocol):
    async def forget(self, user_id: UUID, *, principal_hash: str, job_ids: list[UUID]) -> int: ...


class JobQueue(Protocol):
    async def enqueue_recommendation(self, job_id: UUID, *, correlation_id: str) -> str: ...

    async def enqueue_account_deletion(self, user_id: UUID, *, correlation_id: str) -> str: ...

    async def enqueue_data_export(self, export_id: UUID, *, correlation_id: str) -> str: ...


# ---------------------------------------------------------------- admin (Step 5.11)


@dataclass(frozen=True, slots=True)
class AdminJobRecord:
    """A job as admins see it: no user id, request or result (D-94)."""

    id: UUID
    type: JobType
    status: JobStatus
    stage: JobStage
    attempts: int
    error_code: str | None
    recommendation_id: UUID | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class AgentRunView:
    run_id: UUID
    attempt: int
    status: AgentRunStatus
    http_status: int | None
    error_code: str | None
    duration_ms: int | None
    tool_calls: int | None
    agent_version: str | None
    trace_id: str | None
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdminRecommendationRecord:
    """Diagnostics of one recommendation: no place names, coordinates or text (D-94)."""

    id: UUID
    source: RequestSource
    status: RecommendationStatus
    risk_level: RiskLevel | None
    risk_score: float | None
    risk_confidence: float | None
    recommendation_type: RecommendationType | None
    warning_codes: tuple[str, ...]
    safety_gate_rules: tuple[str, ...]
    overall_is_stale: bool | None
    error_code: str | None
    versions: dict[str, str | None]
    data_freshness: list[dict[str, Any]]
    service_status: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None
    valid_until: datetime | None
    job: AdminJobRecord | None
    agent_runs: tuple[AgentRunView, ...]


@dataclass(frozen=True, slots=True)
class AuditLogRecord:
    id: int
    occurred_at: datetime
    actor_type: ActorType
    actor_ref: str
    action: str
    target_type: str | None
    target_id: str | None
    result: AuditResult
    correlation_id: str
    metadata: dict[str, Any]


class AdminRepository(Protocol):
    async def jobs(
        self,
        *,
        period: TimeRange,
        status: JobStatus | None,
        job_type: JobType | None,
        limit: int,
        cursor: Cursor | None,
    ) -> list[AdminJobRecord]: ...

    async def recommendation(self, recommendation_id: UUID) -> AdminRecommendationRecord | None: ...

    async def audit_logs(
        self, *, period: TimeRange, where: AuditFilter, limit: int, cursor: Cursor | None
    ) -> list[AuditLogRecord]: ...


@dataclass(frozen=True, slots=True)
class TrainingExportRecord:
    id: UUID
    requested_by: str
    status: ExportStatus
    range_from: datetime
    range_to: datetime
    row_count: int | None
    object_key: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None


class TrainingExportRepository(Protocol):
    async def create(
        self, requested_by: str, *, period: TimeRange, now: datetime
    ) -> TrainingExportRecord: ...

    async def get(self, export_id: UUID) -> TrainingExportRecord | None: ...

    async def start(self, export_id: UUID) -> TimeRange | None: ...

    def rows(self, period: TimeRange, *, batch: int) -> AsyncIterator[dict[str, Any]]: ...

    async def finish(
        self,
        export_id: UUID,
        *,
        object_key: str,
        row_count: int,
        now: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def fail(self, export_id: UUID, *, now: datetime) -> None: ...

    async def fail_stuck(self, *, older_than: datetime, now: datetime) -> int: ...


class FileStorePort(Protocol):
    """Object storage for files written to disk first (large exports)."""

    async def put_file(self, key: str, path: str, *, content_type: str) -> None: ...

    async def download_url(self, key: str, *, expires_seconds: int) -> str: ...


class TrainingExportQueue(Protocol):
    async def enqueue_training_export(self, export_id: UUID, *, correlation_id: str) -> str: ...
