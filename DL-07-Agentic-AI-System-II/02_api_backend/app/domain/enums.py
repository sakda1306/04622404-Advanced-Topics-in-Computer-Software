"""Business vocabulary shared by every layer (docs/02_api_spec.md, docs/03_data_design.md)."""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RecommendationType(StrEnum):
    TRAVEL_NORMALLY = "TRAVEL_NORMALLY"
    CHANGE_ROUTE = "CHANGE_ROUTE"
    DELAY_TRAVEL = "DELAY_TRAVEL"
    AVOID_TRAVEL = "AVOID_TRAVEL"


class RecommendationStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL_RESULT = "partial_result"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    RECOMMENDATION = "RECOMMENDATION"
    MESSAGE = "MESSAGE"
    TRIP_ASSESSMENT = "TRIP_ASSESSMENT"
    DATA_EXPORT = "DATA_EXPORT"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    QUEUED = "queued"
    FETCHING_DATA = "fetching_data"
    ASSESSING_RISK = "assessing_risk"
    GENERATING_ADVICE = "generating_advice"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunStatus(StrEnum):
    SUCCESS = "success"
    BAD_RESPONSE = "bad_response"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"
    CIRCUIT_OPEN = "circuit_open"


class TripStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AlertChannel(StrEnum):
    IN_APP = "IN_APP"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class RequestSource(StrEnum):
    RECOMMENDATION = "RECOMMENDATION"
    MESSAGE = "MESSAGE"
    TRIP_ASSESSMENT = "TRIP_ASSESSMENT"
    TRIP_ALERT = "TRIP_ALERT"


class RequestMode(StrEnum):
    AUTO = "auto"
    SYNC = "sync"
    ASYNC = "async"


class FeedbackOutcome(StrEnum):
    FOLLOWED = "FOLLOWED"
    IGNORED = "IGNORED"
    CHANGED_PLAN = "CHANGED_PLAN"
    UNKNOWN = "UNKNOWN"


class ReportType(StrEnum):
    UNSAFE_ADVICE = "UNSAFE_ADVICE"
    INCORRECT_INFO = "INCORRECT_INFO"
    OUTDATED_INFO = "OUTDATED_INFO"
    OTHER = "OTHER"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ExportStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"


class ActorType(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class AuditResult(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    ERROR = "error"


class DataCategory(StrEnum):
    WEATHER = "WEATHER"
    TRANSPORT = "TRANSPORT"
    DISASTER = "DISASTER"
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"


class ServiceState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_USED = "not_used"


class WarningCode(StrEnum):
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    DATA_STALE = "DATA_STALE"
    SERVICE_DEGRADED = "SERVICE_DEGRADED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OUTSIDE_COVERAGE = "OUTSIDE_COVERAGE"


class TravelMode(StrEnum):
    CAR = "CAR"
    TRAIN = "TRAIN"
    BUS = "BUS"
    FLIGHT = "FLIGHT"
    FERRY = "FERRY"
    WALK = "WALK"
    BICYCLE = "BICYCLE"


class AvoidOption(StrEnum):
    TOLLS = "TOLLS"
    HIGHWAYS = "HIGHWAYS"
    FERRIES = "FERRIES"
    NIGHT_TRAVEL = "NIGHT_TRAVEL"


class MobilityNeed(StrEnum):
    WHEELCHAIR = "WHEELCHAIR"
    ELDERLY = "ELDERLY"
    CHILDREN = "CHILDREN"
    PETS = "PETS"


def job_type_for(source: RequestSource) -> JobType:
    """Job type by request source; the worker processes all of them the same way (D-53, D-63)."""
    if source is RequestSource.MESSAGE:
        return JobType.MESSAGE
    if source in (RequestSource.TRIP_ASSESSMENT, RequestSource.TRIP_ALERT):
        return JobType.TRIP_ASSESSMENT
    return JobType.RECOMMENDATION
