from __future__ import annotations

from app.core.errors import ERROR_SPECS, STATUS_TO_CODE, AppError, ErrorCode


def test_every_error_code_has_a_spec() -> None:
    assert set(ERROR_SPECS) == set(ErrorCode)


def test_status_mapping_points_to_matching_status() -> None:
    for status, code in STATUS_TO_CODE.items():
        assert ERROR_SPECS[code].status == status


def test_spec_statuses_match_api_spec_table() -> None:
    expected = {
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.UNAUTHENTICATED: 401,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.IDEMPOTENCY_CONFLICT: 409,
        ErrorCode.VALIDATION_ERROR: 422,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.INTERNAL_ERROR: 500,
        ErrorCode.AGENT_BAD_RESPONSE: 502,
        ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
        ErrorCode.AGENT_TIMEOUT: 504,
    }
    for code, status in expected.items():
        assert ERROR_SPECS[code].status == status


def test_app_error_exposes_status_and_message() -> None:
    err = AppError(ErrorCode.RATE_LIMITED, retry_after=30)

    assert err.status == 429
    assert str(err) == "RATE_LIMITED"
    assert err.retry_after == 30


def test_review_not_pending_is_a_conflict() -> None:
    spec = ERROR_SPECS[ErrorCode.REVIEW_NOT_PENDING]
    assert spec.status == 409
    assert "reviewed" in spec.detail
