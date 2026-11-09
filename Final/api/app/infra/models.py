"""Database tables (Design.md §5). Every user table keys on `user_id` with ON DELETE CASCADE,
so deleting the `users` row removes all of that user's data (DELETE /api/me)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow
from app.core.ids import new_id
from app.infra.db import Base

# JSONB on Postgres (Design.md §5), plain JSON on SQLite in tests.
_JSON = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> str:
    return str(new_id())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(50))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuotaUsage(Base):
    """Requests and tokens one user used on one day (Asia/Bangkok), PRD FR-23."""

    __tablename__ = "quota_usage"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)


class Answer(Base):
    """One saved questionnaire answer, so the user can resume (PRD FR-6)."""

    __tablename__ = "answers"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(_JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RequestLog(Base):
    """One API request for the admin dashboard. No body, no query values, no real path."""

    __tablename__ = "request_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    method: Mapped[str] = mapped_column(String(10))
    route: Mapped[str] = mapped_column(String(200))  # path template, e.g. /api/roles/{role_id}
    status: Mapped[int] = mapped_column(Integer)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class LlmCall(Base):
    """One call to Groq or Jev, including failed attempts. No prompt or answer text."""

    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    task: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(20))  # ok, rate_limited, too_large, timeout, error
    fallback_used: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class RouterLog(Base):
    """One router decision (FR-13). No message text."""

    __tablename__ = "router_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    route: Mapped[str] = mapped_column(String(30))
    layer: Mapped[str] = mapped_column(String(10))  # guard, rules or llm
    confidence: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[int] = mapped_column(Integer)
    tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))  # user or assistant
    text: Mapped[str] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(String(30), nullable=True)  # assistant only
    sources: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, default=list)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    """Where a fact came from, so a profile claim can cite it (Design.md §5)."""

    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))  # cv_line, answer, chat, rag_chunk, user_action
    ref: Mapped[str] = mapped_column(String(100))
    excerpt: Mapped[str] = mapped_column(Text)


class Fact(Base):
    """One thing the user said in chat, checked in Python (domain.chat_facts)."""

    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # skill, experience, education, preference, soft_skill, goal
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[dict[str, Any]] = mapped_column(_JSON)
    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    sections: Mapped[dict[str, Any]] = mapped_column(_JSON)
    profile_version: Mapped[int] = mapped_column(Integer)
    completeness_at_generate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # One hash per input part (CV, each questionnaire section, chat) at generation, so the
    # meter can say which parts changed since (completeness_service.profile_changes).
    input_fingerprints: Mapped[dict[str, str] | None] = mapped_column(_JSON, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RemovedSkill(Base):
    """A skill the user removed, kept whole so a restore brings back its evidence (FR-29, FR-31)."""

    __tablename__ = "removed_skills"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    skill: Mapped[dict[str, Any]] = mapped_column(_JSON)
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EditProposal(Base):
    """A chat edit waiting for the user to confirm it (FR-27)."""

    __tablename__ = "edit_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    changes: Mapped[list[dict[str, Any]]] = mapped_column(_JSON)
    summary_th: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # pending, applied, rejected, expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MatchExplanation(Base):
    """LLM wording of one role's match, with the basis it was written for (Design.md §4.3)."""

    __tablename__ = "match_explanations"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    basis: Mapped[str] = mapped_column(String(64))
    reason_th: Mapped[str] = mapped_column(Text)
    next_steps: Mapped[list[dict[str, Any]]] = mapped_column(_JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CvDocument(Base):
    """The user's CV: extracted text lines (evidence) and parsed fields; the PDF is not kept."""

    __tablename__ = "cv_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    text_lines: Mapped[list[str]] = mapped_column(_JSON)
    parsed: Mapped[dict[str, Any]] = mapped_column(_JSON)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleCache(Base):
    """One copy per role, shared by all users (FR-22a)."""

    __tablename__ = "role_cache"

    role_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refreshing: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(String(40), nullable=True)
    demand: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    salary_advertised: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)


class JobPosting(Base):
    """A Bangkok posting that fits the role. Job-level fields only, no contact details (FR-22e)."""

    __tablename__ = "job_postings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role_id: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text)
    salary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(10), nullable=True)
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshLog(Base):
    """One row per provider run, which counts toward the budgets (FR-22c, REFRESH_DAILY_CAP)."""

    __tablename__ = "refresh_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    day: Mapped[date] = mapped_column(Date, index=True)  # Asia/Bangkok
    role_id: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10))  # ok, failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
