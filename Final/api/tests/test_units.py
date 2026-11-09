"""Units without the app: ids, tokens, passwords, rate limiter, clock, error table."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import jwt
import pytest

from app.core.clock import iso
from app.core.config import Settings
from app.core.errors import ERROR_SPECS, AppError, ErrorCode
from app.core.ids import accept_client_id, new_id
from app.core.logging import REDACTED, redact_processor
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.infra.rate_limit import AttemptLimiter
from tests.conftest import IsolatedSettings


def test_new_id_is_time_ordered_v7() -> None:
    ids = [new_id() for _ in range(2000)]
    assert all(i.version == 7 for i in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize(
    ("value", "accepted"),
    [("abc-123", True), ("a" * 64, True), ("a" * 65, False), ("x y", False), (None, False)],
)
def test_accept_client_id(value: str | None, accepted: bool) -> None:
    assert (accept_client_id(value) is not None) is accepted


def test_token_round_trip_and_tamper() -> None:
    settings = IsolatedSettings(jwt_secret="s" * 32)
    token = create_access_token(settings, "user-1")
    assert decode_access_token(settings, token) == "user-1"
    other = IsolatedSettings(jwt_secret="t" * 32)
    assert decode_access_token(other, token) is None


def test_expired_token_rejected() -> None:
    settings = IsolatedSettings(jwt_secret="s" * 32)
    token = jwt.encode({"sub": "u", "exp": 1}, settings.jwt_secret, algorithm="HS256")
    assert decode_access_token(settings, token) is None


def test_short_secret_refused() -> None:
    with pytest.raises(ValueError, match="jwt_secret"):
        IsolatedSettings(jwt_secret="short")


def test_password_hash() -> None:
    hashed = hash_password("hunter2-long")
    assert verify_password("hunter2-long", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("x" * 100, hashed)


def test_attempt_limiter_window() -> None:
    now = [0.0]
    limiter = AttemptLimiter(limit=2, clock=lambda: now[0])
    limiter.acquire("k")
    limiter.acquire("k")
    with pytest.raises(AppError) as caught:
        limiter.acquire("k")
    assert caught.value.code is ErrorCode.RATE_LIMITED
    assert caught.value.retry_after == 60
    limiter.acquire("other")
    now[0] = 61.0
    limiter.acquire("k")  # new window


def test_attempt_limiter_success_clears() -> None:
    limiter = AttemptLimiter(limit=1, clock=lambda: 0.0)
    limiter.acquire("k")
    limiter.succeed("k")
    limiter.acquire("k")


def _env_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("JWT_SECRET", "s" * 32)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:3000", ["http://localhost:3000"]),
        ("http://a.test, http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://a.test"]', ["http://a.test"]),
    ],
)
def test_cors_origins_from_env(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: list[str]
) -> None:
    settings = _env_settings(monkeypatch, CORS_ALLOWED_ORIGINS=value)
    assert settings.cors_allowed_origins == expected


def test_lower_case_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _env_settings(monkeypatch, LOG_LEVEL="info").log_level == "INFO"


def test_env_example_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    example = Path(__file__).parents[2] / ".env.example"
    for line in example.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and not line.startswith("#"):
            monkeypatch.setenv(name.strip(), value.strip())
    monkeypatch.setenv("JWT_SECRET", "s" * 32)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_allowed_origins == ["http://localhost:3000"]


def test_redaction_keeps_quota_counts() -> None:
    event = redact_processor(
        None,
        "info",
        {
            "event": "x",
            "tokens_used": 120,
            "tokens_remaining": 900,
            "access_token": "abc",
            "nested": {"password": "p", "api_key": "k"},
            "message": "user text",
        },
    )
    assert event["tokens_used"] == 120
    assert event["tokens_remaining"] == 900
    assert event["access_token"] == REDACTED
    assert event["nested"] == {"password": REDACTED, "api_key": REDACTED}
    assert event["message"] == REDACTED


def test_iso_is_bangkok() -> None:
    assert iso(datetime(2026, 11, 3, 7, 5, tzinfo=UTC)) == "2026-11-03T14:05:00+07:00"
    assert iso(datetime(2026, 11, 3, 7, 5)) == "2026-11-03T14:05:00+07:00"


def test_every_code_has_a_spec() -> None:
    assert set(ERROR_SPECS) == set(ErrorCode)


def test_user_facing_messages_say_thai_word_for_skill() -> None:
    # Contract v0.3c: user-facing Thai says "ทักษะ", not the loanword "สกิล".
    assert [code for code, spec in ERROR_SPECS.items() if "สกิล" in spec.message_th] == []


def test_forbidden_is_403() -> None:
    # Contract v0.3d: signed in, but not allowed (admin endpoints).
    spec = ERROR_SPECS[ErrorCode("FORBIDDEN")]
    assert spec.status == 403
    assert spec.message_th


# Keys in .env.example that the api does not read: compose builds the database
# from POSTGRES_*, and API_BASE_URL belongs to web.
NOT_API_SETTINGS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "API_BASE_URL"}


def test_every_env_example_key_is_a_setting() -> None:
    example = Path(__file__).parents[2] / ".env.example"
    keys = {
        line.partition("=")[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    }
    fields = {
        (info.validation_alias if isinstance(info.validation_alias, str) else name).upper()
        for name, info in Settings.model_fields.items()
    }
    assert sorted(keys - NOT_API_SETTINGS - fields) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        ("a@example.com", ["a@example.com"]),
        (" A@Example.com , b@example.com ,", ["a@example.com", "b@example.com"]),
    ],
)
def test_admin_emails_from_env(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: list[str]
) -> None:
    assert _env_settings(monkeypatch, ADMIN_EMAILS=value).admin_emails == expected


def test_engine_hides_sql_parameters() -> None:
    # Database errors must not copy CV text or emails into the log (Design.md §4.1).
    from app.infra.db import create_engine

    engine = create_engine("sqlite+aiosqlite:///:memory:")
    assert engine.sync_engine.hide_parameters is True
