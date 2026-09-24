from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient, ConnectError, Response
from pydantic import SecretStr, ValidationError

from app.core.config import AgentSettings
from app.infrastructure.agent.auth import (
    AgentTokenError,
    ClientCredentials,
    NoAuth,
    StaticToken,
    build_token_provider,
)
from tests.support.clock import FakeClock

TOKEN_URL = "https://idp.example/oauth/token"


def provider(http: AsyncClient, clock: FakeClock) -> ClientCredentials:
    return ClientCredentials(
        http,
        token_url=TOKEN_URL,
        client_id="backend",
        client_secret=SecretStr("s3cret"),
        audience="travel-agent",
        clock=clock,
    )


@respx.mock
async def test_client_credentials_token_is_cached_until_near_expiry() -> None:
    clock = FakeClock()
    route = respx.post(TOKEN_URL).mock(
        side_effect=[
            Response(200, json={"access_token": "t1", "expires_in": 300}),
            Response(200, json={"access_token": "t2", "expires_in": 300}),
        ]
    )
    async with AsyncClient() as http:
        tokens = provider(http, clock)
        first = await tokens.authorization()
        clock.advance(260)
        cached = await tokens.authorization()
        clock.advance(20)  # inside the 30 s safety margin
        refreshed = await tokens.authorization()

    assert (first, cached, refreshed) == ("Bearer t1", "Bearer t1", "Bearer t2")
    assert route.call_count == 2
    sent = route.calls[0].request
    assert sent.headers["authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in sent.content
    assert b"audience=travel-agent" in sent.content


@respx.mock
@pytest.mark.parametrize(
    "outcome",
    [
        Response(500),
        Response(200, json={}),
        Response(200, json={"access_token": ""}),
        Response(200, content=b"nope"),
        ConnectError("down"),
    ],
)
async def test_token_endpoint_failures_raise(outcome: Response | Exception) -> None:
    respx.post(TOKEN_URL).mock(side_effect=[outcome])
    async with AsyncClient() as http:
        with pytest.raises(AgentTokenError):
            await provider(http, FakeClock()).authorization()


async def test_static_and_no_auth() -> None:
    assert await StaticToken(SecretStr("abc")).authorization() == "Bearer abc"
    assert await NoAuth().authorization() is None


async def test_provider_selection() -> None:
    url = "http://agent"
    async with AsyncClient() as http:
        full = AgentSettings(
            agent_service_url=url,
            agent_token_url=TOKEN_URL,
            agent_client_id="id",
            agent_client_secret=SecretStr("x"),
        )
        assert isinstance(build_token_provider(full, http), ClientCredentials)
        static = AgentSettings(agent_service_url=url, agent_service_token=SecretStr("dev"))
        assert isinstance(build_token_provider(static, http), StaticToken)
        assert isinstance(build_token_provider(AgentSettings(agent_service_url=url), http), NoAuth)


def test_partial_client_credentials_are_rejected() -> None:
    with pytest.raises(ValidationError, match="must be set together"):
        AgentSettings(agent_service_url="http://agent", agent_client_id="id")
