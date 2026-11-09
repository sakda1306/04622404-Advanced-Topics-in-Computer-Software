"""Jev in the router's LLM layer, with Groq behind it (Design.md §4.6, §4.7)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.clock import utcnow
from app.core.errors import AppError
from app.infra.db import Base, create_session_factory
from app.infra.jev import JEV_URL, JevClient, build_jev
from app.infra.models import LlmCall, User
from app.router.decide import decide
from app.router.llm_decision import _ROUTES, MIN_JEV_CONFIDENCE, ROUTE_CRITERIA
from app.services import quota_service
from app.services.router_service import route_message
from tests.conftest import make_settings
from tests.router.test_decide import FakeGroq, llm_reply

ASKS_THE_LLM = "ควรไปทางไหนต่อดี"
RULE_HIT = "เงินเดือน QA เท่าไหร่"
GROQ_SAYS_MARKET = '{"route": "market", "confidence": 0.9}'


def jev_reply(choice: str = "salary", confidence: float = 0.9, tokens: int = 600) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "jev-1.14.0",
            "answers": {
                "route": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": confidence,
                    "probabilities": {choice: confidence},
                }
            },
            "usage": {"input_tokens": tokens, "output_tokens": 9},
        },
    )


class FakeJev:
    def __init__(self, tmp_path: Path, groq: FakeGroq) -> None:
        self.settings = make_settings(tmp_path, typesafe_api_key="jev-key", jev_router_enabled=True)
        self.requests: list[httpx.Request] = []
        self.answer: Callable[[], httpx.Response] = jev_reply
        self.sessions = create_session_factory(groq.engine)

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.answer()

        self.client = JevClient(
            self.settings, self.sessions, transport=httpx.MockTransport(handler)
        )

    async def rows(self) -> list[LlmCall]:
        async with self.sessions() as db:
            return list(await db.scalars(select(LlmCall).where(LlmCall.task == "router_jev")))


@pytest.fixture
async def groq(tmp_path: Path) -> AsyncIterator[FakeGroq]:
    fake = FakeGroq(tmp_path)
    async with fake.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield fake
    await fake.engine.dispose()


@pytest.fixture
def jev(tmp_path: Path, groq: FakeGroq) -> FakeJev:
    return FakeJev(tmp_path, groq)


async def test_jev_decides_and_groq_is_not_called(groq: FakeGroq, jev: FakeJev) -> None:
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert (decision.route, decision.confidence, decision.layer) == ("salary", 0.9, "llm")
    assert groq.requests == []


async def test_the_request_holds_the_message_recent_turns_and_every_route(
    groq: FakeGroq, jev: FakeJev
) -> None:
    recent = [{"role": "user", "content": "สาย backend ล่ะ"}]
    await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client, recent=recent)
    request = jev.requests[0]
    body = json.loads(request.content)
    assert str(request.url) == JEV_URL
    assert request.headers["authorization"] == "Bearer jev-key"
    assert body["state"] == {"message": ASKS_THE_LLM, "recent": recent}
    assert body["model"] == "jev-latest"
    assert body["questions"]["route"]["type"] == "choice"
    assert set(body["questions"]["route"]["criteria"]) == set(_ROUTES)


async def test_a_message_without_recent_turns_sends_only_the_message(
    groq: FakeGroq, jev: FakeJev
) -> None:
    await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert json.loads(jev.requests[0].content)["state"] == {"message": ASKS_THE_LLM}


def test_every_route_has_a_description() -> None:
    assert set(ROUTE_CRITERIA) == set(_ROUTES)


async def test_keyword_rules_still_answer_without_jev(groq: FakeGroq, jev: FakeJev) -> None:
    decision = await decide(RULE_HIT, has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.layer == "rules"
    assert jev.requests == []


async def test_guards_still_answer_without_jev(groq: FakeGroq, jev: FakeJev) -> None:
    decision = await decide("   ", has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.layer == "guard"
    assert jev.requests == []


async def test_a_user_without_a_profile_does_not_reach_jev(groq: FakeGroq, jev: FakeJev) -> None:
    decision = await decide(ASKS_THE_LLM, has_profile=False, llm=groq.client, jev=jev.client)
    assert decision.route == "gap_question"
    assert jev.requests == []


async def test_low_confidence_goes_to_groq(groq: FakeGroq, jev: FakeJev) -> None:
    jev.answer = lambda: jev_reply(confidence=MIN_JEV_CONFIDENCE - 0.01)
    groq.script = [llm_reply(GROQ_SAYS_MARKET)]
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.route == "market"
    assert decision.tokens == 50


async def test_when_jev_chooses_clarify_groq_decides(groq: FakeGroq, jev: FakeJev) -> None:
    jev.answer = lambda: jev_reply(choice="clarify", confidence=0.95)
    groq.script = [llm_reply(GROQ_SAYS_MARKET)]
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.route == "market"
    assert len(groq.requests) == 1


async def test_when_both_are_unsure_the_user_is_asked(groq: FakeGroq, jev: FakeJev) -> None:
    jev.answer = lambda: jev_reply(choice="clarify", confidence=0.95)
    groq.script = [llm_reply('{"route": "clarify", "confidence": 0.9}')]
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.route == "clarify"


async def test_a_groq_failure_after_jev_clarify_still_asks_the_user(
    groq: FakeGroq, jev: FakeJev
) -> None:
    jev.answer = lambda: jev_reply(choice="clarify", confidence=0.95)
    groq.script = [httpx.Response(500), httpx.Response(500)]
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert (decision.route, decision.confidence, decision.tokens) == ("clarify", 0.95, 0)


async def test_a_groq_failure_after_a_jev_failure_is_still_an_error(
    groq: FakeGroq, jev: FakeJev
) -> None:
    jev.answer = lambda: httpx.Response(500)
    groq.script = [httpx.Response(500), httpx.Response(500)]
    with pytest.raises(AppError):
        await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)


async def test_confidence_at_the_minimum_keeps_the_choice(groq: FakeGroq, jev: FakeJev) -> None:
    jev.answer = lambda: jev_reply(confidence=MIN_JEV_CONFIDENCE)
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.route == "salary"


def _raises_timeout() -> httpx.Response:
    raise httpx.ReadTimeout("slow")


def _raises_network_error() -> httpx.Response:
    raise httpx.ConnectError("down")


@pytest.mark.parametrize(
    "answer",
    [
        lambda: httpx.Response(500),
        lambda: httpx.Response(529),
        lambda: httpx.Response(429),
        lambda: httpx.Response(401),
        lambda: httpx.Response(200, text="not json"),
        lambda: httpx.Response(200, json={"answers": {}}),
        lambda: jev_reply(choice="made_up_route"),
        lambda: httpx.Response(
            200, text='{"answers": {"route": {"choice": "salary", "confidence": Infinity}}}'
        ),
        _raises_timeout,
        _raises_network_error,
    ],
)
async def test_any_jev_failure_falls_back_to_groq_once(
    groq: FakeGroq, jev: FakeJev, answer: Callable[[], httpx.Response]
) -> None:
    jev.answer = answer
    groq.script = [llm_reply(GROQ_SAYS_MARKET)]
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert decision.route == "market"
    assert decision.tokens == 50
    assert len(jev.requests) == 1
    assert len(groq.requests) == 1


async def test_without_jev_groq_decides(groq: FakeGroq) -> None:
    groq.script = [llm_reply(GROQ_SAYS_MARKET)]
    decision = await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client)
    assert decision.route == "market"


async def test_a_good_call_is_logged_without_any_text(groq: FakeGroq, jev: FakeJev) -> None:
    await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    row = (await jev.rows())[0]
    assert (row.model, row.outcome, row.prompt_tokens, row.completion_tokens) == (
        "jev-1.14.0",
        "ok",
        600,
        0,
    )
    assert row.fallback_used is False
    assert ASKS_THE_LLM not in json.dumps([row.task, row.model, row.outcome])


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (lambda: httpx.Response(429), "rate_limited"),
        (lambda: httpx.Response(500), "error"),
        (_raises_timeout, "timeout"),
    ],
)
async def test_a_failed_call_is_logged_with_its_outcome(
    groq: FakeGroq, jev: FakeJev, answer: Callable[[], httpx.Response], outcome: str
) -> None:
    jev.answer = answer
    groq.script = [llm_reply(GROQ_SAYS_MARKET)]
    await decide(ASKS_THE_LLM, has_profile=True, llm=groq.client, jev=jev.client)
    assert (await jev.rows())[0].outcome == outcome


async def test_jev_tokens_do_not_use_the_groq_quota_but_the_request_counts(
    groq: FakeGroq, jev: FakeJev
) -> None:
    async with jev.sessions() as db:
        user = User(email="a@example.com", password_hash="x", display_name="a", consent_at=utcnow())
        db.add(user)
        await db.commit()
        user_id = user.id
        routed = await route_message(
            db,
            groq.client,
            groq.settings,
            user_id=user_id,
            message=ASKS_THE_LLM,
            has_profile=True,
            jev=jev.client,
        )
        status = await quota_service.get_quota(db, user_id, groq.settings)
    assert routed.decision.route == "salary"
    assert (status.requests_used, status.tokens_used) == (1, 0)


def _settings(tmp_path: Path, **values: Any) -> Any:
    return make_settings(tmp_path, **values)


async def test_build_jev_needs_both_the_switch_and_the_key(groq: FakeGroq, tmp_path: Path) -> None:
    sessions = create_session_factory(groq.engine)
    off = _settings(tmp_path, typesafe_api_key="k", jev_router_enabled=False)
    no_key = _settings(tmp_path, typesafe_api_key="", jev_router_enabled=True)
    on = _settings(tmp_path, typesafe_api_key="k", jev_router_enabled=True)
    assert build_jev(off, sessions) is None
    assert build_jev(no_key, sessions) is None
    client = build_jev(on, sessions)
    assert isinstance(client, JevClient)
    await client.aclose()


def test_jev_is_off_by_default(tmp_path: Path) -> None:
    assert make_settings(tmp_path).jev_router_enabled is False
