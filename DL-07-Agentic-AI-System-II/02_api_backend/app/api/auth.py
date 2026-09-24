"""Authentication, scope checks and per-user rate limits as FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request, Response
from redis.exceptions import RedisError

from app.api.resources import AppResources, get_resources
from app.core.crypto import keyed_hash
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.metrics import RATE_LIMIT_HITS
from app.core.security import Principal, Scope
from app.infrastructure.redis.rate_limiter import RateLimitDecision

log = get_logger(__name__)

_STATE_PRINCIPAL = "principal"
_STATE_RATE_LIMIT = "rate_limit_decision"


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AppError(ErrorCode.UNAUTHENTICATED, headers={"WWW-Authenticate": "Bearer"})
    return token.strip()


def principal_key(resources: AppResources, principal: Principal) -> str:
    """Stable pseudonymous key for a caller, used in Redis key names."""
    return keyed_hash(
        resources.settings.secrets.pseudonym_secret, f"{principal.issuer}|{principal.subject}"
    )


async def enforce_rate_limit(
    resources: AppResources, scope: str, subject: str, limit: int
) -> RateLimitDecision | None:
    """Count one hit; raise 429 when over the limit. Returns None if Redis is down."""
    settings = resources.settings.limits
    try:
        decision = await resources.rate_limiter.hit(
            resources.keys.rate_limit(scope, subject),
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )
    except (RedisError, OSError) as exc:
        log.warning("rate_limit_unavailable", scope=scope, error_type=type(exc).__name__)
        if settings.rate_limit_fail_open:
            return None
        raise AppError(ErrorCode.DEPENDENCY_UNAVAILABLE, retry_after=5) from exc
    if not decision.allowed:
        RATE_LIMIT_HITS.labels(scope=scope).inc()
        raise AppError(
            ErrorCode.RATE_LIMITED,
            retry_after=decision.reset_seconds,
            headers=decision.headers(),
            log_context={"scope": scope},
        )
    return decision


async def authenticate(request: Request) -> Principal:
    """Verify the bearer token once per request and apply the per-user limit (P-30)."""
    cached: Principal | None = getattr(request.state, _STATE_PRINCIPAL, None)
    if cached is not None:
        return cached
    resources = get_resources(request)
    principal = await resources.token_verifier.verify(_bearer_token(request))
    request.state.principal = principal
    decision = await enforce_rate_limit(
        resources,
        "user",
        principal_key(resources, principal),
        resources.settings.limits.rate_limit_user,
    )
    request.state.rate_limit_decision = decision
    return principal


def _apply_rate_limit_headers(request: Request, response: Response) -> None:
    decision: RateLimitDecision | None = getattr(request.state, _STATE_RATE_LIMIT, None)
    if decision is not None:
        response.headers.update(decision.headers())


async def get_principal(request: Request, response: Response) -> Principal:
    principal = await authenticate(request)
    _apply_rate_limit_headers(request, response)
    return principal


def ensure_scopes(principal: Principal, *scopes: Scope) -> None:
    if not principal.has_scopes(scopes):
        raise AppError(
            ErrorCode.FORBIDDEN,
            headers={
                "WWW-Authenticate": (
                    f'Bearer error="insufficient_scope", scope="{" ".join(scopes)}"'
                )
            },
        )


def require_scopes(*scopes: Scope) -> Callable[..., Awaitable[Principal]]:
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        ensure_scopes(principal, *scopes)
        return principal

    return dependency


class RateLimit:
    """Extra per-user limit for an expensive endpoint, e.g. RateLimit("recommend")."""

    def __init__(self, scope: str, limit: Callable[[AppResources], int]) -> None:
        self.scope = scope
        self.limit = limit

    async def __call__(
        self,
        request: Request,
        response: Response,
        principal: Principal = Depends(get_principal),
    ) -> None:
        resources = get_resources(request)
        decision = await enforce_rate_limit(
            resources,
            f"user:{self.scope}",
            principal_key(resources, principal),
            self.limit(resources),
        )
        if decision is not None:
            # The endpoint limit is the tighter one, so report it to the client.
            response.headers.update(decision.headers())


recommend_rate_limit = RateLimit(
    "recommend", lambda resources: resources.settings.limits.rate_limit_recommend
)
