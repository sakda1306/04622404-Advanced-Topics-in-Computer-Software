"""Chat, history and feedback (CONTRACT.md §1) and the router call (§2)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import HistoryMessage, Route, Source, Text, TokenUsage, Trace

MAX_MESSAGE_CHARS = 2000


class ChatRequest(BaseModel):
    session_id: UUID | None = None
    message: Text = Field(max_length=MAX_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be empty")
        return stripped


class ChatResponse(BaseModel):
    request_id: str
    session_id: UUID
    message_id: UUID
    answer: str
    sources: list[Source]
    route: Route
    engines_used: list[str]
    confidence: float | None
    latency_ms: int
    data_as_of: str | None
    created_at: str
    trace: Trace | None


class SessionItem(BaseModel):
    session_id: UUID
    title: str
    updated_at: str


class SessionList(BaseModel):
    sessions: list[SessionItem]


class MessageOut(BaseModel):
    message_id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source]
    route: Route | None
    rating: int | None
    created_at: str


class History(BaseModel):
    session_id: UUID
    messages: list[MessageOut]


class FeedbackRequest(BaseModel):
    message_id: UUID
    rating: Literal[1, -1]
    comment: Text | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------- api -> router


class RouteUser(BaseModel):
    id: UUID
    favorite_team_id: int | None
    language: str


class RouteContext(BaseModel):
    season: str
    current_matchweek: int | None
    now: str
    last_ingest_at: str | None = None


class RouteRequest(BaseModel):
    request_id: str
    session_id: UUID
    user: RouteUser
    query: str
    history: list[HistoryMessage]
    context: RouteContext


class RouteResponse(BaseModel):
    request_id: str | None = None
    answer: str
    sources: list[Source] = Field(default_factory=list)
    route: Route
    engines_used: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reasoning: str | None = None
    latency_ms: int | None = None
    token_usage: TokenUsage | None = None
    trace: Trace | None = None
