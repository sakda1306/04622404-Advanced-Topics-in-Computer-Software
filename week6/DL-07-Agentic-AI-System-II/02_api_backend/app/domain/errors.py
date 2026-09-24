"""Domain errors; the API layer maps them to Problem Details."""

from __future__ import annotations

from dataclasses import dataclass


class DomainError(Exception):
    """Base class for rule violations detected in the domain layer."""


@dataclass(frozen=True, slots=True)
class FieldIssue:
    field: str
    code: str
    message: str


class InvalidInput(DomainError):
    def __init__(self, issues: list[FieldIssue]) -> None:
        super().__init__(", ".join(f"{i.field}: {i.code}" for i in issues))
        self.issues = issues
