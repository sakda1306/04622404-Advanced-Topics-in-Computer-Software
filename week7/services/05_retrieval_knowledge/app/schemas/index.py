"""Index management requests and responses (CONTRACT §6)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.kb.documents import Document, doc_id_matches
from app.schemas.search import Category, Text

Origin = Literal[
    "kb", "football-data.org", "api-football", "generated", "openfootball", "fjelstul", "wikidata"
]

MAX_DOCUMENTS = 100


class DocumentIn(BaseModel):
    # An unknown key is a caller bug; dropping it silently would lose data.
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(max_length=128)
    title: Text = Field(max_length=300)
    text: Text
    category: Category
    origin: Origin
    season: str | None = Field(default=None, pattern=r"^\d{4}$")
    matchweek: int | None = Field(default=None, ge=1, le=38)
    team_ids: list[int] = Field(default_factory=list)
    date: dt.date | None = None
    fetched_at: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=2048)
    topic: str | None = Field(default=None, max_length=200)

    @field_validator("title", "text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def _doc_id_fits_category(self) -> DocumentIn:
        # Locked format per category (§6): the id is what makes an upsert replace, not add.
        if not doc_id_matches(self.category, self.doc_id):
            raise ValueError(f"doc_id does not match the {self.category} format")
        return self

    def to_document(self) -> Document:
        return Document(
            doc_id=self.doc_id,
            title=self.title,
            category=self.category,
            origin=self.origin,
            text=self.text,
            season=self.season,
            matchweek=self.matchweek,
            team_ids=tuple(self.team_ids),
            date=self.date.isoformat() if self.date else None,
            fetched_at=self.fetched_at,
            url=self.url,
            topic=self.topic,
        )


class UpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=64)
    documents: list[DocumentIn] = Field(min_length=1, max_length=MAX_DOCUMENTS)


class UpsertResponse(BaseModel):
    request_id: str
    upserted: int
    chunks: int
    index_version: str | None


class DeleteResponse(BaseModel):
    deleted: bool


class StatsResponse(BaseModel):
    documents: int
    chunks: int
    by_category: dict[str, int]
    index_version: str | None


class RebuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=64)
    category: Category | None = None  # none = every category


class RebuildAccepted(BaseModel):
    job_id: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    started_at: str | None
    finished_at: str | None
    detail: str | None
