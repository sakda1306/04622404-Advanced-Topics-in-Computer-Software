"""Import every model so Base.metadata is complete (used by Alembic and tests)."""

from app.infrastructure.db.base import Base
from app.infrastructure.db.models.audit import AuditLogModel
from app.infrastructure.db.models.conversation import ConversationModel, MessageModel
from app.infrastructure.db.models.job import AgentRunModel, DataExportModel, JobModel
from app.infrastructure.db.models.mlops import (
    FeedbackModel,
    PredictionRecordModel,
    TrainingExportModel,
)
from app.infrastructure.db.models.recommendation import RecommendationModel
from app.infrastructure.db.models.reference import CoverageAreaModel, EmergencyDefaultModel
from app.infrastructure.db.models.request import TravelRequestModel
from app.infrastructure.db.models.trip import TripModel
from app.infrastructure.db.models.user import UserModel

__all__ = [
    "AgentRunModel",
    "AuditLogModel",
    "Base",
    "ConversationModel",
    "CoverageAreaModel",
    "DataExportModel",
    "EmergencyDefaultModel",
    "FeedbackModel",
    "JobModel",
    "MessageModel",
    "PredictionRecordModel",
    "RecommendationModel",
    "TrainingExportModel",
    "TravelRequestModel",
    "TripModel",
    "UserModel",
]
