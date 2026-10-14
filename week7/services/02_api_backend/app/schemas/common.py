"""Shared objects from CONTRACT.md: Source, TokenUsage, Trace, HistoryMessage."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Route = Literal["football_rag", "general_ai", "local_ai", "clarify", "decline", "chat"]
Category = Literal[
    "trivia", "match_report", "standings", "fixtures", "weekly_report", "player", "historical"
]
Origin = Literal["kb", "football-data.org", "api-football", "generated"]
Layer = Literal["guard", "rules", "classifier", "llm"]
Fallback = Literal["retrieval_empty", "retrieval_down", "llm_fallback_provider"]


def _reject_nul(value: str) -> str:
    # Postgres text cannot store U+0000; refuse it here instead of failing at the database.
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


Text = Annotated[str, AfterValidator(_reject_nul)]
"""Any user-supplied string that is stored in or compared against the database."""


class PassThrough(BaseModel):
    """Objects produced by other services: unknown fields are kept, not dropped."""

    model_config = ConfigDict(extra="allow")


class Source(PassThrough):
    ref: int
    doc_id: str
    title: str = ""
    category: str | None = None
    origin: str | None = None
    season: str | None = None
    matchweek: int | None = None
    team_ids: list[int] = Field(default_factory=list)
    fetched_at: str | None = None
    url: str | None = None


class TokenUsage(PassThrough):
    input: int = 0
    output: int = 0


class TraceStep(PassThrough):
    name: str
    ms: int | float = 0


class Trace(PassThrough):
    decided_at_layer: str | None = None
    intent: str | None = None
    rewritten_query: str | None = None
    filters: dict[str, object] | None = None
    fallback: str | None = None
    steps: list[TraceStep] = Field(default_factory=list)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Ok(BaseModel):
    ok: bool = True


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
