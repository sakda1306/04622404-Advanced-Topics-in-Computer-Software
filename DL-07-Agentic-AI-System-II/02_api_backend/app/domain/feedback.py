"""Feedback on a recommendation and safety review routing (docs/02_api_spec.md 7.3, D-67)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.domain.enums import FeedbackOutcome, ReportType, ReviewStatus
from app.domain.errors import FieldIssue, InvalidInput
from app.domain.sanitizer import clean_text

COMMENT_MAX_CHARS = 1000
NOTE_MAX_CHARS = 1000
RATING_RANGE = (1, 5)

# Reports that may mean the assistant put someone at risk go to a human first.
_NEEDS_REVIEW = frozenset({ReportType.UNSAFE_ADVICE, ReportType.INCORRECT_INFO})


@dataclass(frozen=True, slots=True)
class FeedbackInput:
    rating: int | None = None
    helpful: bool | None = None
    outcome: FeedbackOutcome = FeedbackOutcome.UNKNOWN
    report_type: ReportType | None = None
    comment: str | None = None


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"

    @property
    def status(self) -> ReviewStatus:
        return ReviewStatus(self.value)


def _text(value: str | None, field: str, limit: int) -> tuple[str | None, list[FieldIssue]]:
    cleaned = clean_text(value)
    if cleaned is not None and len(cleaned) > limit:
        return cleaned, [FieldIssue(field, "too_long", f"at most {limit} characters")]
    return cleaned, []


def check_feedback(raw: FeedbackInput) -> FeedbackInput:
    comment, issues = _text(raw.comment, "comment", COMMENT_MAX_CHARS)
    low, high = RATING_RANGE
    if raw.rating is not None and not low <= raw.rating <= high:
        issues.append(FieldIssue("rating", "out_of_range", f"must be {low}-{high}"))
    result = replace(raw, comment=comment)
    if result == FeedbackInput():
        issues.append(
            FieldIssue(
                "feedback", "feedback_empty", "give a rating, an outcome, a report or a comment"
            )
        )
    if issues:
        raise InvalidInput(issues)
    return result


def review_status_for(report_type: ReportType | None) -> ReviewStatus:
    return ReviewStatus.PENDING if report_type in _NEEDS_REVIEW else ReviewStatus.NOT_REQUIRED


def check_review_note(note: str | None) -> str | None:
    cleaned, issues = _text(note, "note", NOTE_MAX_CHARS)
    if issues:
        raise InvalidInput(issues)
    return cleaned
