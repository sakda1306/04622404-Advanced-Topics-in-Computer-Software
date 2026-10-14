import httpx
import pytest

from app.config import Settings
from app.football import PrimaryThrottle, fetch_primary


class FakeSleep:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def headers(available: int, reset: int = 60) -> httpx.Headers:
    return httpx.Headers(
        {"x-requests-available-minute": str(available), "X-RequestCounter-Reset": str(reset)}
    )


async def test_waits_for_reset_when_no_requests_remain():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    throttle.observe(headers(available=0, reset=42))
    await throttle.wait()
    assert sleep.calls == [42]


async def test_does_not_wait_while_requests_remain():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    throttle.observe(headers(available=3))
    await throttle.wait()
    assert sleep.calls == []


async def test_does_not_wait_before_any_response_or_without_headers():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    await throttle.wait()
    throttle.observe(httpx.Headers())
    await throttle.wait()
    assert sleep.calls == []


async def test_waits_only_once_per_exhaustion():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    throttle.observe(headers(available=0, reset=10))
    await throttle.wait()
    await throttle.wait()
    assert sleep.calls == [10]


async def test_rate_limited_response_without_headers_waits_a_full_minute():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    throttle.block(httpx.Headers())
    await throttle.wait()
    assert sleep.calls == [60]


async def test_fetch_primary_pauses_before_next_call_when_quota_is_spent():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    seen: list[str] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={}, headers=headers(available=0, reset=7))

    settings = Settings(football_data_api_key="test-token", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        await fetch_primary(http, settings, "competitions/PL/teams", "2026", "r1", throttle)
        assert sleep.calls == []
        await fetch_primary(http, settings, "competitions/PL/matches", "2026", "r1", throttle)

    assert sleep.calls == [7]
    assert seen == ["/v4/competitions/PL/teams", "/v4/competitions/PL/matches"]


async def test_fetch_primary_backs_off_a_full_minute_after_429_then_succeeds():
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    responses = [
        httpx.Response(429, json={"message": "slow down"}),
        httpx.Response(200, json={"ok": True}, headers=headers(available=9)),
    ]

    def upstream(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    settings = Settings(football_data_api_key="test-token", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        data = await fetch_primary(http, settings, "competitions/PL/teams", "2026", "r1", throttle)

    assert data == {"ok": True}
    assert sleep.calls == [60]


async def test_fetch_primary_still_works_without_a_throttle():
    def upstream(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    settings = Settings(football_data_api_key="test-token", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as http:
        data = await fetch_primary(http, settings, "competitions/PL/teams", "2026", "r1")
    assert data == {"ok": True}


@pytest.mark.parametrize("value", ["abc", "", "-1"])
async def test_ignores_malformed_header_values(value):
    sleep = FakeSleep()
    throttle = PrimaryThrottle(sleep=sleep)
    throttle.observe(httpx.Headers({"x-requests-available-minute": value}))
    await throttle.wait()
    assert sleep.calls == []


async def test_service_shares_one_throttle_across_primary_calls(monkeypatch):
    from app import service as service_module
    from app.service import FootballService

    captured = []

    class Stop(Exception):
        pass

    async def fake_fetch(http, settings, path, season, request_id, throttle=None):
        captured.append(throttle)
        if len(captured) == 2:
            raise Stop
        return {}

    monkeypatch.setattr(service_module, "fetch_primary", fake_fetch)
    async with httpx.AsyncClient() as http:
        service = FootballService(Settings(_env_file=None), None, http)
        with pytest.raises(Stop):
            await service._ingest_primary("r1")

    assert isinstance(captured[0], PrimaryThrottle)
    assert captured[0] is captured[1]
