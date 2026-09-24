from __future__ import annotations

import httpx
import pytest

from app.core.config import AuthSettings, RedisSettings, Settings
from app.core.crypto import keyed_hash
from app.core.security import build_token_verifier
from scripts import dev_token

DEV_KEY = "d" * 40


async def test_script_prints_a_verifiable_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEV_JWT_SIGNING_KEY", DEV_KEY)

    code = dev_token.main(["--sub", "tester", "--scope", "travel:read"])

    token = capsys.readouterr().out.strip()
    assert code == 0
    async with httpx.AsyncClient() as http:
        principal = await build_token_verifier(AuthSettings(), http).verify(token)
    assert principal.subject == "tester"
    assert principal.scopes == {"travel:read"}


def test_script_refuses_without_key(capsys: pytest.CaptureFixture[str]) -> None:
    assert dev_token.main([]) == 2
    assert "DEV_JWT_SIGNING_KEY" in capsys.readouterr().err


def test_script_refuses_in_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")

    assert dev_token.main([]) == 2
    assert capsys.readouterr().out == ""


# ------------------------------------------------------------------ related settings


def test_redis_urls_are_derived_from_redis_url() -> None:
    from pydantic import SecretStr

    settings = RedisSettings(redis_url=SecretStr("redis://user:pw@cache:6379/0?ssl=true"))

    assert settings.core_url() == "redis://user:pw@cache:6379/0?ssl=true"
    assert settings.cache_url() == "redis://user:pw@cache:6379/1?ssl=true"
    assert settings.broker_url() == "redis://user:pw@cache:6379/2?ssl=true"


def test_explicit_redis_urls_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_CACHE_URL", "redis://other:6380/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "")

    settings = Settings().redis

    assert settings.cache_url() == "redis://other:6380/0"
    assert settings.broker_url() == "redis://localhost:6379/2"


def test_keyed_hash_depends_on_secret() -> None:
    from pydantic import SecretStr

    a = keyed_hash(SecretStr("one"), "10.0.0.1")
    b = keyed_hash(SecretStr("two"), "10.0.0.1")

    assert a != b
    assert len(a) == 64
    assert keyed_hash(None, "x") == keyed_hash(None, "x")
