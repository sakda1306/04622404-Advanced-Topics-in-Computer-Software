from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
import respx
from joserfc import jwt
from joserfc.jwk import OctKey, RSAKey
from pydantic import SecretStr

from app.core.config import AuthSettings, Settings
from app.core.errors import AppError, ErrorCode
from app.core.security import (
    JWKSKeyProvider,
    Principal,
    StaticKeyProvider,
    TokenVerifier,
    build_token_verifier,
    issue_dev_token,
)
from tests.support.auth import TokenFactory, generate_signing_key, jwks_document, public_key_set
from tests.support.clock import FakeClock

ISSUER = "https://idp.example"
AUDIENCE = "travel-safety-api"
JWKS_URL = "https://idp.example/jwks"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def tokens(signing_key: RSAKey) -> TokenFactory:
    return TokenFactory(signing_key, ISSUER, AUDIENCE)


@pytest.fixture
def verifier(signing_key: RSAKey, clock: FakeClock) -> TokenVerifier:
    return TokenVerifier(
        StaticKeyProvider(public_key_set(signing_key)),
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=["RS256"],
        leeway_seconds=30,
        clock=clock,
    )


async def _rejected(verifier: TokenVerifier, token: str) -> AppError:
    with pytest.raises(AppError) as info:
        await verifier.verify(token)
    assert info.value.code is ErrorCode.UNAUTHENTICATED
    assert info.value.headers["WWW-Authenticate"].startswith("Bearer")
    return info.value


# ------------------------------------------------------------------ happy path


async def test_valid_token_gives_principal(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock
) -> None:
    token = tokens(
        "user-42", ["travel:read", "travel:write"], now=clock.now(), jti="t-1", email="a@b.c"
    )

    principal = await verifier.verify(token)

    assert principal.subject == "user-42"
    assert principal.issuer == ISSUER
    assert principal.scopes == {"travel:read", "travel:write"}
    assert principal.token_id == "t-1"
    assert principal.expires_at == clock.now() + timedelta(minutes=15)
    assert "a@b.c" not in repr(principal)


async def test_scp_list_and_audience_list_are_supported(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock
) -> None:
    token = tokens(now=clock.now(), scope=None, scp=["travel:read"], aud=["other", AUDIENCE])

    principal = await verifier.verify(token)

    assert principal.scopes == {"travel:read"}


async def test_small_clock_skew_is_tolerated(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock
) -> None:
    token = tokens(now=clock.now(), lifetime=timedelta(minutes=1))
    clock.advance(60 + 20)  # expired 20 s ago, leeway is 30 s

    assert (await verifier.verify(token)).subject == "user-1"


def test_has_scopes() -> None:
    principal = Principal("s", "i", frozenset({"a", "b"}), expires_at=None)  # type: ignore[arg-type]

    assert principal.has_scopes(["a"])
    assert not principal.has_scopes(["a", "c"])


# ------------------------------------------------------------------ rejections


async def test_expired_token_is_rejected(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock
) -> None:
    token = tokens(now=clock.now(), lifetime=timedelta(minutes=1))
    clock.advance(60 + 31)

    await _rejected(verifier, token)


async def test_token_not_yet_valid_is_rejected(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock
) -> None:
    nbf = int((clock.now() + timedelta(minutes=5)).timestamp())

    await _rejected(verifier, tokens(now=clock.now(), nbf=nbf))


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.example"},
        {"aud": "another-api"},
        {"sub": None},
        {"sub": ""},
        {"exp": None},
        {"iss": None},
        {"aud": None},
    ],
)
async def test_wrong_or_missing_claims_are_rejected(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock, claims: dict[str, Any]
) -> None:
    await _rejected(verifier, tokens(now=clock.now(), **claims))


async def test_token_signed_by_unknown_key_is_rejected(
    verifier: TokenVerifier, tokens: TokenFactory, clock: FakeClock
) -> None:
    attacker = generate_signing_key(kid="test-key")  # same kid, different key

    await _rejected(verifier, tokens(now=clock.now(), key=attacker))


@pytest.mark.filterwarnings("ignore::joserfc.errors.SecurityWarning")
async def test_hs256_signed_with_public_key_is_rejected(
    verifier: TokenVerifier, signing_key: RSAKey, clock: FakeClock
) -> None:
    # Algorithm confusion: use the public key bytes as an HMAC secret.
    secret = OctKey.import_key(signing_key.as_pem(private=False))
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "exp": 4102444800}
    token = jwt.encode({"alg": "HS256", "kid": "test-key"}, claims, secret)

    await _rejected(verifier, token)


async def test_unsigned_token_is_rejected(verifier: TokenVerifier) -> None:
    token = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0."

    await _rejected(verifier, token)


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "a.b.c.d", "x" * 9000])
async def test_malformed_tokens_are_rejected(verifier: TokenVerifier, token: str) -> None:
    await _rejected(verifier, token)


# ------------------------------------------------------------------ JWKS


def _provider(clock: FakeClock, http: httpx.AsyncClient, jwks_url: str | None) -> JWKSKeyProvider:
    return JWKSKeyProvider(
        http,
        issuer=ISSUER,
        jwks_url=jwks_url,
        cache_seconds=600,
        min_refresh_seconds=60,
        clock=clock,
    )


@respx.mock
async def test_jwks_is_discovered_and_cached(
    signing_key: RSAKey, tokens: TokenFactory, clock: FakeClock
) -> None:
    discovery = respx.get(f"{ISSUER}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={"jwks_uri": JWKS_URL})
    )
    jwks = respx.get(JWKS_URL).mock(
        return_value=httpx.Response(200, json=jwks_document(signing_key))
    )
    async with httpx.AsyncClient() as http:
        verifier = TokenVerifier(
            _provider(clock, http, None),
            issuer=ISSUER,
            audience=AUDIENCE,
            algorithms=["RS256"],
            clock=clock,
        )
        for _ in range(3):
            await verifier.verify(tokens(now=clock.now()))
        clock.advance(601)
        await verifier.verify(tokens(now=clock.now()))

    assert discovery.call_count == 1
    assert jwks.call_count == 2


@respx.mock
async def test_unknown_kid_triggers_one_refresh_for_key_rotation(
    signing_key: RSAKey, tokens: TokenFactory, clock: FakeClock
) -> None:
    rotated = generate_signing_key(kid="rotated")
    jwks = respx.get(JWKS_URL).mock(
        side_effect=[
            httpx.Response(200, json=jwks_document(signing_key)),
            httpx.Response(200, json=jwks_document(signing_key, rotated)),
        ]
    )
    async with httpx.AsyncClient() as http:
        verifier = TokenVerifier(
            _provider(clock, http, JWKS_URL),
            issuer=ISSUER,
            audience=AUDIENCE,
            algorithms=["RS256"],
            clock=clock,
        )
        await verifier.verify(tokens(now=clock.now()))
        clock.advance(61)
        principal = await verifier.verify(tokens("rotated-user", now=clock.now(), key=rotated))

    assert principal.subject == "rotated-user"
    assert jwks.call_count == 2


@respx.mock
async def test_unknown_kid_refresh_is_throttled(
    signing_key: RSAKey, tokens: TokenFactory, clock: FakeClock
) -> None:
    stranger = generate_signing_key(kid="stranger")
    jwks = respx.get(JWKS_URL).mock(
        return_value=httpx.Response(200, json=jwks_document(signing_key))
    )
    async with httpx.AsyncClient() as http:
        verifier = TokenVerifier(
            _provider(clock, http, JWKS_URL),
            issuer=ISSUER,
            audience=AUDIENCE,
            algorithms=["RS256"],
            clock=clock,
        )
        for _ in range(5):
            await _rejected(verifier, tokens(now=clock.now(), key=stranger))

    assert jwks.call_count == 1


@respx.mock
async def test_issuer_outage_without_cached_keys_is_503(clock: FakeClock) -> None:
    respx.get(JWKS_URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as http:
        provider = _provider(clock, http, JWKS_URL)
        with pytest.raises(AppError) as info:
            await provider.get_keys()

    assert info.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE


@respx.mock
async def test_issuer_outage_keeps_serving_cached_keys(
    signing_key: RSAKey, tokens: TokenFactory, clock: FakeClock
) -> None:
    respx.get(JWKS_URL).mock(
        side_effect=[
            httpx.Response(200, json=jwks_document(signing_key)),
            httpx.ConnectError("down"),
        ]
    )
    async with httpx.AsyncClient() as http:
        verifier = TokenVerifier(
            _provider(clock, http, JWKS_URL),
            issuer=ISSUER,
            audience=AUDIENCE,
            algorithms=["RS256"],
            clock=clock,
        )
        await verifier.verify(tokens(now=clock.now()))
        clock.advance(601)
        principal = await verifier.verify(tokens(now=clock.now()))

    assert principal.subject == "user-1"


@respx.mock
async def test_discovery_without_jwks_uri_is_503(clock: FakeClock) -> None:
    respx.get(f"{ISSUER}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={})
    )
    async with httpx.AsyncClient() as http:
        with pytest.raises(AppError):
            await _provider(clock, http, None).get_keys()


# ------------------------------------------------------------------ dev tokens


DEV_KEY = "k" * 40


async def test_dev_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_JWT_SIGNING_KEY", DEV_KEY)
    settings = Settings().auth
    async with httpx.AsyncClient() as http:
        verifier = build_token_verifier(settings, http)
        token = issue_dev_token(settings, subject="dev-user", scopes=["travel:read"])
        principal = await verifier.verify(token)

    assert principal.subject == "dev-user"
    assert principal.scopes == {"travel:read"}


async def test_rs256_verifier_rejects_dev_tokens(signing_key: RSAKey) -> None:
    dev_settings = AuthSettings(
        jwt_issuer=ISSUER, jwt_audience=AUDIENCE, dev_jwt_signing_key=SecretStr(DEV_KEY)
    )
    token = issue_dev_token(dev_settings, subject="x", scopes=[])
    verifier = TokenVerifier(
        StaticKeyProvider(public_key_set(signing_key)),
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithms=["RS256"],
    )

    await _rejected(verifier, token)


def test_dev_token_needs_dev_key() -> None:
    settings = AuthSettings(jwt_issuer=ISSUER, jwt_audience=AUDIENCE)

    with pytest.raises(RuntimeError):
        issue_dev_token(settings, subject="x", scopes=[])


async def test_production_verifier_uses_jwks() -> None:
    settings = AuthSettings(jwt_issuer=ISSUER, jwt_audience=AUDIENCE)
    async with httpx.AsyncClient() as http:
        verifier = build_token_verifier(settings, http)

    assert isinstance(verifier._keys, JWKSKeyProvider)


@pytest.mark.parametrize("value", ["HS256", "none", "RS256,HS512", ""])
def test_symmetric_or_empty_algorithms_are_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("JWT_ALGORITHMS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_short_dev_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("DEV_JWT_SIGNING_KEY", "short")
    with pytest.raises(ValidationError):
        Settings()
