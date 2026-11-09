"""The interface every job data provider follows (Design.md §7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    """A failed fetch. `code` is short and safe to store: never a response body or a token."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Posting:
    """Only the job-level fields the feature needs, so contact details never enter (FR-22e)."""

    source: str
    title: str
    company: str
    location: str
    province: str
    salary_text: str
    posted_text: str
    url: str
    text: str  # description and qualifications, read for skills and never stored


class JobDataProvider(Protocol):
    name: str

    async def fetch_postings(self, keyword: str, limit: int) -> list[Posting]: ...
