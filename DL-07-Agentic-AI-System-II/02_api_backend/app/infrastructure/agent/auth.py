"""Credentials the backend presents to the Agent (docs/02_api_spec.md section 9.1)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Protocol

import httpx
from pydantic import SecretStr

from app.core.clock import Clock, SystemClock
from app.core.config import AgentSettings

# Refresh a little early so a token never expires while a request is in flight.
_EXPIRY_MARGIN = timedelta(seconds=30)


class AgentTokenError(Exception):
    """The token endpoint failed; callers treat the Agent as unavailable."""


class AgentTokenProvider(Protocol):
    async def authorization(self) -> str | None: ...


class NoAuth:
    async def authorization(self) -> str | None:
        return None


class StaticToken:
    """Shared token for development setups."""

    def __init__(self, token: SecretStr) -> None:
        self._token = token

    async def authorization(self) -> str | None:
        return f"Bearer {self._token.get_secret_value()}"


class ClientCredentials:
    """OAuth2 client credentials grant with an in-memory token cache."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        token_url: str,
        client_id: str,
        client_secret: SecretStr,
        audience: str,
        clock: Clock | None = None,
    ) -> None:
        self._http = http
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._audience = audience
        self._clock = clock or SystemClock()
        self._token: str | None = None
        self._expires_at = self._clock.now()
        self._lock = asyncio.Lock()

    async def authorization(self) -> str | None:
        if self._token is None or self._clock.now() >= self._expires_at - _EXPIRY_MARGIN:
            async with self._lock:
                if self._token is None or self._clock.now() >= self._expires_at - _EXPIRY_MARGIN:
                    await self._refresh()
        return f"Bearer {self._token}"

    async def _refresh(self) -> None:
        try:
            response = await self._http.post(
                self._token_url,
                data={"grant_type": "client_credentials", "audience": self._audience},
                auth=(self._client_id, self._client_secret.get_secret_value()),
            )
            response.raise_for_status()
            body = response.json()
            token = body["access_token"]
            lifetime = int(body.get("expires_in", 300))
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AgentTokenError(type(exc).__name__) from exc
        if not isinstance(token, str) or not token:
            raise AgentTokenError("empty access_token")
        self._token = token
        self._expires_at = self._clock.now() + timedelta(seconds=lifetime)


def build_token_provider(
    settings: AgentSettings, http: httpx.AsyncClient, clock: Clock | None = None
) -> AgentTokenProvider:
    if settings.agent_token_url and settings.agent_client_id and settings.agent_client_secret:
        return ClientCredentials(
            http,
            token_url=settings.agent_token_url,
            client_id=settings.agent_client_id,
            client_secret=settings.agent_client_secret,
            audience=settings.agent_audience,
            clock=clock,
        )
    if settings.agent_service_token is not None:
        return StaticToken(settings.agent_service_token)
    return NoAuth()
