"""Access token verification (OAuth2 / OIDC, docs/02_api_spec.md NFR-03).

Production verifies asymmetric tokens against the issuer's JWKS. Dev/test may use a
shared HS256 key (DEV_JWT_SIGNING_KEY) instead; Settings forbids that key elsewhere.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

import httpx
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError, JoseError
from joserfc.jwk import KeySet, OctKey

from app.core.clock import Clock, SystemClock
from app.core.config import AuthSettings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

log = get_logger(__name__)

MAX_TOKEN_LENGTH = 8192
DEV_KEY_ID = "dev"
DEV_ALGORITHM = "HS256"
# Malformed input can surface as plain ValueError/TypeError from the decoder.
_DECODE_ERRORS = (JoseError, ValueError, TypeError)


class Scope(StrEnum):
    TRAVEL_READ = "travel:read"
    TRAVEL_WRITE = "travel:write"
    PROFILE_READ = "profile:read"
    PROFILE_WRITE = "profile:write"
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    SAFETY_REVIEW = "safety:review"


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    issuer: str
    scopes: frozenset[str]
    expires_at: datetime
    token_id: str | None = None
    email: str | None = field(default=None, repr=False)

    def has_scopes(self, required: Iterable[str]) -> bool:
        return set(required) <= self.scopes


def unauthenticated(detail: str | None = None) -> AppError:
    return AppError(
        ErrorCode.UNAUTHENTICATED,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


class KeyProvider(Protocol):
    async def get_keys(self, *, force_refresh: bool = False) -> KeySet: ...


class StaticKeyProvider:
    def __init__(self, keys: KeySet) -> None:
        self._keys = keys

    async def get_keys(self, *, force_refresh: bool = False) -> KeySet:
        return self._keys


class JWKSKeyProvider:
    """Fetches and caches the issuer's signing keys.

    A token with an unknown `kid` triggers a refresh (key rotation), limited to one
    refresh per `min_refresh_seconds` so bad tokens cannot flood the issuer.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        issuer: str,
        jwks_url: str | None,
        cache_seconds: int,
        min_refresh_seconds: int,
        clock: Clock | None = None,
    ) -> None:
        self._http = http
        self._issuer = issuer.rstrip("/")
        self._jwks_url = jwks_url
        self._cache_seconds = cache_seconds
        self._min_refresh_seconds = min_refresh_seconds
        self._clock = clock or SystemClock()
        self._keys: KeySet | None = None
        self._fetched_at = float("-inf")
        self._lock = asyncio.Lock()

    async def get_keys(self, *, force_refresh: bool = False) -> KeySet:
        age = self._clock.monotonic() - self._fetched_at
        if self._keys is not None and age < self._cache_seconds and not force_refresh:
            return self._keys
        if self._keys is not None and force_refresh and age < self._min_refresh_seconds:
            return self._keys
        async with self._lock:
            # Another request may have refreshed while we waited.
            age = self._clock.monotonic() - self._fetched_at
            if self._keys is not None and age < self._min_refresh_seconds:
                return self._keys
            try:
                self._keys = await self._fetch()
            except (httpx.HTTPError, ValueError, JoseError) as exc:
                log.warning("jwks_fetch_failed", error_type=type(exc).__name__)
                if self._keys is None:
                    raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=30) from exc
                # Keep serving the previous keys; retry after the minimum interval.
            self._fetched_at = self._clock.monotonic()
            return self._keys

    async def _fetch(self) -> KeySet:
        url = self._jwks_url or await self._discover_jwks_url()
        response = await self._http.get(url)
        response.raise_for_status()
        return KeySet.import_key_set(response.json())

    async def _discover_jwks_url(self) -> str:
        response = await self._http.get(f"{self._issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        url = response.json().get("jwks_uri")
        if not isinstance(url, str) or not url:
            raise ValueError("discovery document has no jwks_uri")
        self._jwks_url = url
        return url


class TokenVerifier:
    def __init__(
        self,
        keys: KeyProvider,
        *,
        issuer: str,
        audience: str,
        algorithms: Collection[str],
        leeway_seconds: int = 30,
        clock: Clock | None = None,
    ) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._algorithms = list(algorithms)
        self._leeway = leeway_seconds
        self._clock = clock or SystemClock()

    async def verify(self, token: str) -> Principal:
        if not token or len(token) > MAX_TOKEN_LENGTH or token.count(".") != 2:
            raise unauthenticated()
        claims = await self._decode(token)
        registry = jwt.JWTClaimsRegistry(
            now=lambda: int(self._clock.now().timestamp()),
            leeway=self._leeway,
            iss={"essential": True, "value": self._issuer},
            aud={"essential": True, "value": self._audience},
            exp={"essential": True},
            sub={"essential": True},
        )
        try:
            registry.validate(claims)
        except JoseError as exc:
            raise unauthenticated() from exc
        return _principal_from(claims)

    async def _decode(self, token: str) -> dict[str, Any]:
        keys = await self._keys.get_keys()
        try:
            return _decode_with(token, keys, self._algorithms)
        except _DECODE_ERRORS as exc:
            if not isinstance(exc, InvalidKeyIdError):
                raise unauthenticated() from exc
        # The issuer may have rotated its keys since we cached them.
        keys = await self._keys.get_keys(force_refresh=True)
        try:
            return _decode_with(token, keys, self._algorithms)
        except _DECODE_ERRORS as exc:
            raise unauthenticated() from exc


def _decode_with(token: str, keys: KeySet, algorithms: list[str]) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(token, keys, algorithms=algorithms).claims
    return claims


def _principal_from(claims: dict[str, Any]) -> Principal:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise unauthenticated()
    return Principal(
        subject=subject,
        issuer=str(claims["iss"]),
        scopes=_scopes_from(claims),
        expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
        token_id=claims.get("jti") if isinstance(claims.get("jti"), str) else None,
        email=claims.get("email") if isinstance(claims.get("email"), str) else None,
    )


def _scopes_from(claims: dict[str, Any]) -> frozenset[str]:
    # "scope" is a space-separated string (RFC 8693); some issuers use an "scp" list.
    raw = claims.get("scope", claims.get("scp", ""))
    if isinstance(raw, str):
        return frozenset(raw.split())
    if isinstance(raw, list):
        return frozenset(item for item in raw if isinstance(item, str))
    return frozenset()


def dev_key_set(signing_key: str) -> KeySet:
    key = OctKey.import_key(signing_key, {"kid": DEV_KEY_ID, "alg": DEV_ALGORITHM, "use": "sig"})
    return KeySet([key])


def build_token_verifier(
    settings: AuthSettings, http: httpx.AsyncClient, clock: Clock | None = None
) -> TokenVerifier:
    if settings.dev_jwt_signing_key is not None:
        provider: KeyProvider = StaticKeyProvider(
            dev_key_set(settings.dev_jwt_signing_key.get_secret_value())
        )
        algorithms = [DEV_ALGORITHM]
    else:
        provider = JWKSKeyProvider(
            http,
            issuer=settings.jwt_issuer,
            jwks_url=settings.jwks_url,
            cache_seconds=settings.jwks_cache_seconds,
            min_refresh_seconds=settings.jwks_min_refresh_seconds,
            clock=clock,
        )
        algorithms = settings.jwt_algorithms
    return TokenVerifier(
        provider,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        algorithms=algorithms,
        leeway_seconds=settings.jwt_leeway_seconds,
        clock=clock,
    )


def issue_dev_token(
    settings: AuthSettings,
    *,
    subject: str,
    scopes: Iterable[str],
    lifetime: timedelta = timedelta(minutes=15),  # P-10
    clock: Clock | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Sign a short-lived token with DEV_JWT_SIGNING_KEY (dev/test only)."""
    if settings.dev_jwt_signing_key is None:
        raise RuntimeError("DEV_JWT_SIGNING_KEY is not configured")
    now = (clock or SystemClock()).now()
    claims: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": subject,
        "scope": " ".join(sorted(set(scopes))),
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        **(extra_claims or {}),
    }
    keys = dev_key_set(settings.dev_jwt_signing_key.get_secret_value())
    return jwt.encode({"alg": DEV_ALGORITHM, "kid": DEV_KEY_ID}, claims, keys)
