"""Team nicknames from 07 `GET /football/teams`, with the bundled file as fallback."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.search.aliases import AliasProvider, keep_aliases_fresh, load_alias_file, refresh_aliases
from tests.conftest import TEST_DATA

FALLBACK = str(TEST_DATA / "team_aliases.json")
TEAMS_FROM_07: dict[str, Any] = {
    "teams": [
        {
            "team_id": 57,
            "name": "Arsenal FC",
            "short_name": "Arsenal",
            "tla": "ARS",
            "aliases": ["ปืนใหญ่", "เดอะกันเนอร์ส"],
            "crest_url": "https://crests.example/57.png",
        }
    ]
}


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://football-data:8000"
    )


def answering(status: int, body: Any = None) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/football/teams"
        return httpx.Response(status, json=body)

    return handler


def provider() -> AliasProvider:
    return AliasProvider(load_alias_file(FALLBACK))


def test_the_fallback_file_answers_before_07_is_reached() -> None:
    assert "Arsenal" in provider().expand("ปืนใหญ่ชนะไหม")


async def test_a_new_alias_from_07_is_used() -> None:
    aliases = provider()
    assert aliases.expand("เดอะกันเนอร์สชนะไหม") == []
    async with client_for(answering(200, TEAMS_FROM_07)) as client:
        assert await refresh_aliases(aliases, client) is True
    assert "Arsenal" in aliases.expand("เดอะกันเนอร์สชนะไหม")


@pytest.mark.parametrize(
    "handler",
    [
        answering(503, {"code": "UPSTREAM_UNAVAILABLE"}),
        answering(200, {"teams": []}),
        answering(200, {"teams": [{"team_id": 57, "name": "Arsenal FC", "aliases": []}]}),
        answering(200, {"unexpected": True}),
        answering(200, {"teams": [{"name": "no id"}]}),
    ],
)
async def test_a_bad_answer_keeps_the_aliases_in_use(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    aliases = provider()
    async with client_for(handler) as client:
        assert await refresh_aliases(aliases, client) is False
    assert "Man United" in aliases.expand("แมนยูแพ้")


async def test_07_down_keeps_the_aliases_in_use() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    aliases = provider()
    async with client_for(down) as client:
        assert await refresh_aliases(aliases, client) is False
    assert "Man United" in aliases.expand("แมนยูแพ้")


async def test_keep_fresh_retries_sooner_after_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([answering(503), answering(200, TEAMS_FROM_07)])
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return next(answers)(request)

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    aliases = provider()
    async with client_for(handler) as client:
        with pytest.raises(asyncio.CancelledError):
            await keep_aliases_fresh(aliases, client, every=3600, retry_after=60)
    assert waits == [60, 3600]
    assert "Arsenal" in aliases.expand("เดอะกันเนอร์ส")


async def test_keep_fresh_survives_an_unexpected_error(monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []

    async def crash(*_args: object) -> bool:
        raise RuntimeError("tokenizer crashed")

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr("app.search.aliases.refresh_aliases", crash)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    async with client_for(answering(200, TEAMS_FROM_07)) as client:
        with pytest.raises(asyncio.CancelledError):
            await keep_aliases_fresh(provider(), client, every=3600, retry_after=60)
    assert waits == [60]


async def test_teams_07_does_not_cover_keep_their_bundled_nicknames() -> None:
    # 07 (#6) sends Thai nicknames for 8 teams only; the other teams must keep theirs.
    aliases = provider()
    async with client_for(answering(200, TEAMS_FROM_07)) as client:
        assert await refresh_aliases(aliases, client) is True
    assert "Man United" in aliases.expand("แมนยูแพ้")
    assert "Tottenham" in aliases.expand("ไก่เดือยทองชนะ")


async def test_nicknames_of_the_same_team_are_merged() -> None:
    aliases = provider()
    async with client_for(answering(200, TEAMS_FROM_07)) as client:
        await refresh_aliases(aliases, client)
    # Arsenal: "เดอะกันเนอร์ส" comes from 07, "gunners" only from the bundled file.
    assert "Arsenal" in aliases.expand("เดอะกันเนอร์สชนะไหม")
    assert "Arsenal" in aliases.expand("did the gunners win")


async def test_a_team_only_07_knows_is_added() -> None:
    villa = {"team_id": 58, "name": "Aston Villa FC", "short_name": "Aston Villa"}
    feed = {"teams": [{**villa, "aliases": ["สิงห์ผงาด"]}]}
    aliases = provider()
    async with client_for(answering(200, feed)) as client:
        await refresh_aliases(aliases, client)
    assert "Aston Villa" in aliases.expand("สิงห์ผงาดชนะไหม")
    assert "Arsenal" in aliases.expand("ปืนใหญ่ชนะไหม")
