from __future__ import annotations

from typing import Any

import pytest

from app import serve


@pytest.fixture
def uvicorn_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_run(app: str, **kwargs: Any) -> None:
        calls.append({"app": app, **kwargs})

    monkeypatch.setattr("uvicorn.run", fake_run)
    return calls


def test_invalid_config_exits_before_starting_workers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    uvicorn_calls: list[dict[str, Any]],
) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("RATE_LIMIT_USER", "s3cr3t-looking-value")

    code = serve.main(["--workers", "2"])

    assert code == serve.EXIT_CONFIG_ERROR
    assert uvicorn_calls == []
    err = capsys.readouterr().err
    assert "cors_allowed_origins" in err
    assert "rate_limit_user" in err
    assert "s3cr3t-looking-value" not in err
    assert "Traceback" not in err


def test_cross_group_rule_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    uvicorn_calls: list[dict[str, Any]],
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DEV_JWT_SIGNING_KEY", "local-only-key")

    assert serve.main([]) == serve.EXIT_CONFIG_ERROR
    assert uvicorn_calls == []
    err = capsys.readouterr().err
    assert "DEV_JWT_SIGNING_KEY" in err
    assert "local-only-key" not in err


def test_valid_config_starts_uvicorn_with_factory(uvicorn_calls: list[dict[str, Any]]) -> None:
    code = serve.main(["--workers", "3", "--port", "9000"])

    assert code == 0
    assert uvicorn_calls == [
        {
            "app": "app.main:create_app",
            "factory": True,
            "host": "0.0.0.0",
            "port": 9000,
            "workers": 3,
            "reload": False,
            "reload_dirs": None,
            "access_log": False,
            "proxy_headers": True,
            "forwarded_allow_ips": "127.0.0.1",
        }
    ]


def test_reload_mode_uses_single_process(uvicorn_calls: list[dict[str, Any]]) -> None:
    serve.main(["--reload", "--workers", "4"])

    call = uvicorn_calls[0]
    assert call["reload"] is True
    assert call["workers"] == 1
    assert call["reload_dirs"] == ["app"]
