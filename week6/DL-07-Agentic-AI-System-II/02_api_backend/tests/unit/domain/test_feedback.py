from __future__ import annotations

import pytest

from app.domain.enums import FeedbackOutcome, ReportType, ReviewStatus
from app.domain.errors import InvalidInput
from app.domain.feedback import (
    FeedbackInput,
    ReviewDecision,
    check_feedback,
    check_review_note,
    review_status_for,
)


def issues(call: object) -> dict[str, str]:
    assert callable(call)
    with pytest.raises(InvalidInput) as info:
        call()
    return {i.field: i.code for i in info.value.issues}


def test_comment_is_cleaned() -> None:
    result = check_feedback(FeedbackInput(rating=4, comment="  good\x00 trains ​"))
    assert result.comment == "good trains"
    assert check_feedback(FeedbackInput(rating=4, comment="   ")).comment is None


def test_limits() -> None:
    assert issues(lambda: check_feedback(FeedbackInput(rating=0))) == {"rating": "out_of_range"}
    assert issues(lambda: check_feedback(FeedbackInput(rating=6))) == {"rating": "out_of_range"}
    assert issues(lambda: check_feedback(FeedbackInput(comment="x" * 1001))) == {
        "comment": "too_long"
    }
    assert check_feedback(FeedbackInput(rating=1, comment="x" * 1000)).rating == 1


def test_feedback_must_say_something() -> None:
    assert issues(lambda: check_feedback(FeedbackInput())) == {"feedback": "feedback_empty"}
    assert issues(lambda: check_feedback(FeedbackInput(comment=" "))) == {
        "feedback": "feedback_empty"
    }


@pytest.mark.parametrize(
    "raw",
    [
        FeedbackInput(rating=5),
        FeedbackInput(helpful=False),
        FeedbackInput(outcome=FeedbackOutcome.IGNORED),
        FeedbackInput(report_type=ReportType.OTHER),
        FeedbackInput(comment="thanks"),
    ],
)
def test_any_signal_is_enough(raw: FeedbackInput) -> None:
    assert check_feedback(raw) == raw


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (None, ReviewStatus.NOT_REQUIRED),
        (ReportType.OTHER, ReviewStatus.NOT_REQUIRED),
        (ReportType.OUTDATED_INFO, ReviewStatus.NOT_REQUIRED),
        (ReportType.UNSAFE_ADVICE, ReviewStatus.PENDING),
        (ReportType.INCORRECT_INFO, ReviewStatus.PENDING),
    ],
)
def test_review_routing(report: ReportType | None, expected: ReviewStatus) -> None:
    assert review_status_for(report) is expected


def test_review_decisions_use_the_stored_values() -> None:
    assert ReviewDecision.APPROVED.value == ReviewStatus.APPROVED.value
    assert ReviewDecision.REJECTED.value == ReviewStatus.REJECTED.value
    assert ReviewDecision.APPROVED.status is ReviewStatus.APPROVED


def test_review_note() -> None:
    assert check_review_note(None) is None
    assert check_review_note("  confirmed\x07 ") == "confirmed"
    assert issues(lambda: check_review_note("x" * 1001)) == {"note": "too_long"}
