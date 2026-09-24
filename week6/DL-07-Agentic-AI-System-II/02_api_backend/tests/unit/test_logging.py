from __future__ import annotations

import json

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.logging import REDACTED, configure_logging, get_logger, redact_processor


def test_redacts_sensitive_top_level_keys() -> None:
    event = {
        "event": "login",
        "authorization": "Bearer abc",
        "access_token": "abc",
        "user_email": "someone@example.com",
        "lat": 13.75,
        "question": "is it safe?",
        "status": 200,
    }

    out = redact_processor(None, "info", event)

    assert out["event"] == "login"
    assert out["status"] == 200
    for key in ("authorization", "access_token", "user_email", "lat", "question"):
        assert out[key] == REDACTED


def test_redacts_nested_values() -> None:
    event = {
        "event": "agent_call",
        "payload": {
            "origin": {"lat": 1, "lon": 2},
            "legs": [{"api_key": "k", "mode": "TRAIN"}],
            "language": "th",
        },
    }

    out = redact_processor(None, "info", event)

    assert out["payload"]["origin"] == REDACTED
    assert out["payload"]["legs"] == [{"api_key": REDACTED, "mode": "TRAIN"}]
    assert out["payload"]["language"] == "th"


def test_json_log_output_is_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_output=True)

    get_logger("test").info("user_event", password="hunter2", route="/v1/x")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "user_event"
    assert record["password"] == REDACTED
    assert record["route"] == "/v1/x"
    assert "hunter2" not in line


def test_level_filter_drops_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="WARNING", json_output=True)

    get_logger("test").info("hidden_event")

    assert "hidden_event" not in capsys.readouterr().out


def test_database_exception_messages_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_output=True)
    error = DBAPIError("SELECT 1", {"q": "secret-question"}, Exception("Key (q)=(secret-question)"))

    try:
        raise error
    except DBAPIError:
        get_logger("test").exception("db_failed")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert "secret-question" not in line
    assert "DBAPIError" in record["exception"]
    assert "test_database_exception_messages_are_redacted" in record["exception"]


def test_other_exception_messages_are_kept(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", json_output=True)

    try:
        raise ValueError("plain failure")
    except ValueError:
        get_logger("test").exception("failed")

    assert "plain failure" in capsys.readouterr().out
