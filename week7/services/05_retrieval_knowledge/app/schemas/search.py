"""POST /search request and response (CONTRACT §4) and the Source object (§0)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.search.hybrid import Mode
from app.search.snapshot import SearchFilters

Category = Literal[
    "trivia", "match_report", "standings", "fixtures", "weekly_report", "player", "historical"
]


def _reject_nul(value: str) -> str:
    # Lesson from 02: refuse U+0000 at the edge instead of failing deeper down.
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


Text = Annotated[str, AfterValidator(_reject_nul)]
TopicName = Annotated[str, Field(min_length=1, max_length=200)]


class SearchFiltersIn(BaseModel):
    # An unknown key is a caller bug; ignoring it would silently return unfiltered results.
    model_config = ConfigDict(extra="forbid")

    category: list[Category] | None = Field(default=None, min_length=1)
    season: str | None = Field(default=None, pattern=r"^\d{4}$")
    matchweek: int | None = Field(default=None, ge=1, le=38)
    team_ids: list[int] | None = Field(default=None, min_length=1)
    date_from: date | None = None
    date_to: date | None = None
    topic: list[TopicName] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _date_order(self) -> SearchFiltersIn:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self

    def to_filters(self) -> SearchFilters:
        return SearchFilters(
            category=tuple(self.category) if self.category else None,
            season=self.season,
            matchweek=self.matchweek,
            team_ids=tuple(self.team_ids) if self.team_ids else None,
            date_from=self.date_from.isoformat() if self.date_from else None,
            date_to=self.date_to.isoformat() if self.date_to else None,
            topic=tuple(self.topic) if self.topic else None,
        )


class SearchRequest(BaseModel):
    # A mistyped key (e.g. "filter") would otherwise return unfiltered results.
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=64)
    query: Text = Field(max_length=1000)
    query_original: Text | None = Field(default=None, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: SearchFiltersIn = Field(default_factory=SearchFiltersIn)
    mode: Mode = "hybrid"

    @field_validator("filters", mode="before")
    @classmethod
    def _null_means_no_filter(cls, value: object) -> object:
        # Optional in CONTRACT §4; callers that dump None send `"filters": null`.
        return {} if value is None else value

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped


class SourceOut(BaseModel):
    ref: int
    doc_id: str
    title: str
    category: str
    origin: str
    season: str | None
    matchweek: int | None
    team_ids: list[int]
    fetched_at: str | None
    url: str | None
    topic: str | None


class ChunkOut(BaseModel):
    chunk_id: str
    text: str
    score: float
    bm25_score: float | None
    vector_score: float | None
    rerank_score: float | None
    source: SourceOut


class SearchResponse(BaseModel):
    request_id: str
    chunks: list[ChunkOut]
    latency_ms: int
    index_version: str | None
