"""Admin objects (CONTRACT.md §1.1)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Category, Source, Text, TokenUsage, Trace


class UserRef(BaseModel):
    id: UUID
    username: str


class LatencySummary(BaseModel):
    p50: int
    p95: int


class FeedbackSummary(BaseModel):
    up: int
    down: int


class Stats(BaseModel):
    days: int
    total_messages: int
    by_route: dict[str, int]
    by_layer: dict[str, int]
    feedback: FeedbackSummary
    latency_ms: LatencySummary
    fallback_count: int


class FeedbackItem(BaseModel):
    message_id: UUID
    rating: int
    comment: str | None
    created_at: str
    user: UserRef
    question: str | None
    answer_preview: str
    route: str | None
    fallback: str | None


class AdminMessage(BaseModel):
    message_id: UUID
    request_id: str | None
    session_id: UUID
    user: UserRef
    question: str | None
    answer: str
    sources: list[Source]
    route: str | None
    confidence: float | None
    reasoning: str | None
    trace: Trace | None
    token_usage: TokenUsage | None
    latency_ms: int | None
    rating: int | None
    comment: str | None
    created_at: str


class LogItem(BaseModel):
    request_id: str
    message_id: UUID | None
    user_id: UUID
    route: str | None
    decided_at_layer: str | None
    fallback: str | None
    status: int
    error_code: str | None
    latency_ms: int
    created_at: str


class AuditEntryOut(BaseModel):
    audit_id: UUID
    actor: UserRef
    action: str
    target: str | None
    detail: dict[str, Any]
    request_id: str | None
    created_at: str


class AdminUser(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: Literal["user", "admin"]
    disabled: bool
    created_at: str
    last_login_at: str | None
    message_count: int


class IngestRequest(BaseModel):
    scope: Literal["fixtures", "details", "all"]


class GenerateReportRequest(BaseModel):
    season: str | None = Field(default=None, pattern=r"^\d{4}$")
    matchweek: int | None = Field(default=None, ge=1, le=38)


class ReportPatch(BaseModel):
    title: Text | None = Field(default=None, min_length=1, max_length=200)
    markdown: Text | None = Field(default=None, min_length=1, max_length=50_000)


class UserPatch(BaseModel):
    role: Literal["user", "admin"] | None = None
    disabled: bool | None = None


class ReindexRequest(BaseModel):
    category: Category | None = None
