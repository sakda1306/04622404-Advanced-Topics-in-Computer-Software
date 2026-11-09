"""Groq client (Design.md §4.7, PRD NFR Reliability): the real client over a fake HTTP transport."""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.clock import utcnow
from app.core.errors import AppError, ErrorCode
from app.core.ids import request_id_var
from app.infra.db import Base, create_engine, create_session_factory
from app.infra.llm import GroqClient
from app.infra.models import LlmCall, User
from tests.conftest import make_settings

MAIN, ROUTER, FALLBACK = "main-model", "router-model", "fallback-model"
MESSAGES = [{"role": "user", "content": "ข้อความส่วนตัวของผู้ใช้"}]


def ok(text: str = "คำตอบ", prompt: int = 10, completion: int = 5, finish: str = "stop") -> Any:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": finish}
            ],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    )


def status(code: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after else {}
    return httpx.Response(code, headers=headers, json={"error": {"message": "ข้อความส่วนตัวของผู้ใช้"}})


class Harness:
    """A real GroqClient and database; only the network and the waiting are replaced."""

    def __init__(self, tmp_path: Path) -> None:
        self.settings = make_settings(
            tmp_path,
            groq_api_key="test-key",
            groq_model=MAIN,
            groq_router_model=ROUTER,
            groq_fallback_model=FALLBACK,
        )
        self.engine = create_engine(self.settings.database_url)
        self.sessions = create_session_factory(self.engine)
        self.requests: list[httpx.Request] = []
        self.waits: list[float] = []
        self.script: list[Any] = []

    def models_called(self) -> list[str]:
        return [json.loads(r.content)["model"] for r in self.requests]

    def body(self, index: int = 0) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.requests[index].content)
        return loaded

    def client(self, **overrides: Any) -> GroqClient:
        settings = self.settings.model_copy(update=overrides)

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            response: httpx.Response = step
            return response

        async def fake_sleep(seconds: float) -> None:
            self.waits.append(seconds)

        return GroqClient(
            settings,
            self.sessions,
            transport=httpx.MockTransport(handler),
            sleep=fake_sleep,
        )

    async def rows(self) -> list[LlmCall]:
        async with self.sessions() as db:
            result = await db.scalars(select(LlmCall).order_by(LlmCall.id))
            return list(result)


@pytest.fixture
async def llm(tmp_path: Path) -> AsyncIterator[Harness]:
    harness = Harness(tmp_path)
    async with harness.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield harness
    await harness.engine.dispose()


async def _fails_with(client: GroqClient, code: ErrorCode, **kwargs: Any) -> None:
    with pytest.raises(AppError) as caught:
        await client.complete(messages=MESSAGES, task="explain", **kwargs)
    assert caught.value.code == code


# --- choosing the model and building the request


async def test_main_tier_uses_the_main_model(llm: Harness) -> None:
    llm.script = [ok("สวัสดี", prompt=12, completion=3)]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert result.text == "สวัสดี"
    assert result.model == MAIN
    assert result.tokens == 15
    assert result.fallback_used is False
    assert llm.models_called() == [MAIN]
    assert llm.body()["messages"] == MESSAGES


async def test_router_tier_uses_the_router_model(llm: Harness) -> None:
    llm.script = [ok()]
    await llm.client().complete(messages=MESSAGES, task="router", tier="router")
    assert llm.models_called() == [ROUTER]


async def test_request_carries_the_key_and_limits(llm: Harness) -> None:
    llm.script = [ok()]
    await llm.client().complete(messages=MESSAGES, task="explain", max_tokens=77, temperature=0.5)
    request = llm.requests[0]
    assert request.headers["authorization"] == "Bearer test-key"
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert llm.body()["max_completion_tokens"] == 77
    assert llm.body()["temperature"] == 0.5


async def test_gpt_oss_hides_its_reasoning_and_other_models_get_no_such_fields(
    llm: Harness,
) -> None:
    llm.script = [ok(), ok()]
    await llm.client(groq_model="openai/gpt-oss-120b").complete(messages=MESSAGES, task="explain")
    assert llm.body(0)["include_reasoning"] is False
    assert llm.body(0)["reasoning_effort"] == "low"
    await llm.client().complete(messages=MESSAGES, task="explain")
    assert not {"include_reasoning", "reasoning_effort"} & set(llm.body(1))


async def test_thinking_text_never_reaches_the_answer(llm: Harness) -> None:
    llm.script = [ok("<think>คิดก่อน\nหลายบรรทัด</think>\n\nคำตอบจริง")]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert result.text == "คำตอบจริง"


async def test_json_mode_returns_parsed_data(llm: Harness) -> None:
    llm.script = [ok('<think>x</think>{"route": "salary", "confidence": 0.9}')]
    result = await llm.client().complete(messages=MESSAGES, task="router", json_mode=True)
    assert result.data == {"route": "salary", "confidence": 0.9}
    assert llm.body()["response_format"] == {"type": "json_object"}


async def test_plain_mode_has_no_response_format(llm: Harness) -> None:
    llm.script = [ok()]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert result.data is None
    assert "response_format" not in llm.body()


# --- retry, fallback, failure (Design.md §4.7)


async def test_429_retries_once_after_waiting_then_succeeds(llm: Harness) -> None:
    llm.script = [status(429, retry_after="2"), ok()]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.models_called() == [MAIN, MAIN]
    assert llm.waits == [2.0]
    assert result.fallback_used is False


async def test_429_without_retry_after_waits_the_default(llm: Harness) -> None:
    llm.script = [status(429), ok()]
    await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.waits == [1.0]


async def test_429_twice_moves_to_the_fallback_model(llm: Harness) -> None:
    llm.script = [status(429, retry_after="1"), status(429, retry_after="1"), ok()]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.models_called() == [MAIN, MAIN, FALLBACK]
    assert result.fallback_used is True
    assert result.model == FALLBACK


async def test_long_retry_after_skips_the_retry_and_the_wait(llm: Harness) -> None:
    # A daily limit can ask for minutes; waiting would miss the 15 s target for nothing.
    llm.script = [status(429, retry_after="600"), ok()]
    await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.models_called() == [MAIN, FALLBACK]
    assert llm.waits == []


async def test_413_goes_straight_to_the_fallback_model(llm: Harness) -> None:
    llm.script = [status(413), ok()]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.models_called() == [MAIN, FALLBACK]
    assert llm.waits == []
    assert result.fallback_used is True


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(lambda: status(500), id="500"),
        pytest.param(lambda: status(503), id="503"),
        pytest.param(lambda: httpx.ConnectError("no route"), id="network"),
    ],
)
async def test_server_errors_retry_then_fall_back(llm: Harness, failure: Callable[[], Any]) -> None:
    llm.script = [failure(), failure(), ok()]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.models_called() == [MAIN, MAIN, FALLBACK]
    assert result.fallback_used is True


@pytest.mark.parametrize(
    "bad_answer",
    [
        pytest.param(lambda: ok(""), id="empty"),
        pytest.param(lambda: ok("   "), id="blank"),
        pytest.param(lambda: ok("<think>หมด token ระหว่างคิด</think>"), id="only-thinking"),
        pytest.param(lambda: ok("ตัดกลางค", finish="length"), id="cut-off"),
        pytest.param(lambda: httpx.Response(200, json={"choices": []}), id="no-choices"),
        pytest.param(lambda: httpx.Response(200, text="not json"), id="broken-body"),
    ],
)
async def test_unusable_answer_skips_the_retry_and_falls_back(
    llm: Harness, bad_answer: Callable[[], Any]
) -> None:
    llm.script = [bad_answer(), ok()]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert llm.models_called() == [MAIN, FALLBACK]
    assert result.fallback_used is True


async def test_invalid_json_in_json_mode_falls_back(llm: Harness) -> None:
    llm.script = [ok("ไม่ใช่ JSON"), ok('{"route": "market"}')]
    result = await llm.client().complete(messages=MESSAGES, task="router", json_mode=True)
    assert result.data == {"route": "market"}
    assert result.fallback_used is True


async def test_json_mode_rejects_a_value_that_is_not_an_object(llm: Harness) -> None:
    llm.script = [ok("[1, 2]"), ok('{"route": "market"}')]
    result = await llm.client().complete(messages=MESSAGES, task="router", json_mode=True)
    assert result.data == {"route": "market"}


async def test_all_attempts_failing_is_llm_unavailable(llm: Harness) -> None:
    llm.script = [status(429, "1"), status(429, "1"), status(429, "1")]
    await _fails_with(llm.client(), ErrorCode.LLM_UNAVAILABLE)
    assert llm.models_called() == [MAIN, MAIN, FALLBACK]  # the fallback model gets one try


async def test_same_fallback_model_is_not_called_twice_more(llm: Harness) -> None:
    # The router model doubles as the fallback (Design.md §4.7).
    llm.script = [status(429, "1"), status(429, "1")]
    client = llm.client(groq_fallback_model=ROUTER)
    await _fails_with(client, ErrorCode.LLM_UNAVAILABLE, tier="router")
    assert llm.models_called() == [ROUTER, ROUTER]


@pytest.mark.parametrize("code", [401, 403])
async def test_bad_key_stops_at_once(llm: Harness, code: int) -> None:
    llm.script = [status(code)]
    await _fails_with(llm.client(), ErrorCode.LLM_UNAVAILABLE)
    assert llm.models_called() == [MAIN]


async def test_timeout_is_llm_timeout_with_no_more_attempts(llm: Harness) -> None:
    llm.script = [httpx.ReadTimeout("slow")]
    await _fails_with(llm.client(), ErrorCode.LLM_TIMEOUT)
    assert llm.models_called() == [MAIN]


async def test_timeout_on_the_fallback_model_is_llm_timeout(llm: Harness) -> None:
    llm.script = [status(413), httpx.ReadTimeout("slow")]
    await _fails_with(llm.client(), ErrorCode.LLM_TIMEOUT)


async def test_each_attempt_only_gets_the_time_that_is_left(
    llm: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = itertools.count(step=10.0)  # every reading of the clock is 10 s later
    clock = SimpleNamespace(monotonic=lambda: next(ticks), perf_counter=time.perf_counter)
    monkeypatch.setattr("app.infra.llm.time", clock)
    llm.script = [status(413), ok()]
    await llm.client(llm_timeout_s=30.0).complete(messages=MESSAGES, task="explain")
    # Deadline read at 0 s = 30 s. First attempt reads 10 s, second reads 20 s.
    assert llm.requests[0].extensions["timeout"]["read"] == 20.0
    assert llm.requests[1].extensions["timeout"]["read"] == 10.0


async def _router_call(client: GroqClient) -> Any:
    return await client.complete(messages=MESSAGES, task="router", tier="router")


async def test_a_stuck_router_call_is_cut_short_and_retried(llm: Harness) -> None:
    llm.script = [httpx.ReadTimeout("stuck"), ok()]
    result = await _router_call(llm.client())
    assert result.text == "คำตอบ"
    assert llm.models_called() == [ROUTER, ROUTER]
    assert [r.extensions["timeout"]["read"] for r in llm.requests] == [7.0, 7.0]


async def test_a_router_call_stuck_twice_goes_to_the_fallback_model(llm: Harness) -> None:
    llm.script = [httpx.ReadTimeout("stuck"), httpx.ConnectTimeout("stuck"), ok()]
    result = await _router_call(llm.client())
    assert result.fallback_used is True
    assert llm.models_called() == [ROUTER, ROUTER, FALLBACK]


async def test_a_router_call_with_no_other_model_ends_as_llm_timeout(llm: Harness) -> None:
    llm.script = [httpx.ReadTimeout("stuck"), httpx.ReadTimeout("stuck")]
    with pytest.raises(AppError) as caught:
        await _router_call(llm.client(groq_fallback_model=ROUTER))
    assert caught.value.code is ErrorCode.LLM_TIMEOUT
    assert llm.models_called() == [ROUTER, ROUTER]


async def test_each_stuck_attempt_is_logged(llm: Harness) -> None:
    llm.script = [httpx.ReadTimeout("stuck"), ok()]
    await _router_call(llm.client())
    async with llm.sessions() as db:
        outcomes = [row.outcome for row in await db.scalars(select(LlmCall))]
    assert sorted(outcomes) == ["ok", "timeout"]


async def test_a_router_timeout_never_runs_past_the_whole_deadline(llm: Harness) -> None:
    llm.script = [httpx.ReadTimeout("stuck")]
    with pytest.raises(AppError) as caught:
        await _router_call(llm.client(llm_timeout_s=5.0))
    assert caught.value.code is ErrorCode.LLM_TIMEOUT
    assert llm.models_called() == [ROUTER]  # the whole 5 s went on one attempt
    assert llm.requests[0].extensions["timeout"]["read"] <= 5.0


async def test_the_main_model_keeps_all_its_time(llm: Harness) -> None:
    llm.script = [ok()]
    await llm.client(llm_timeout_s=30.0).complete(messages=MESSAGES, task="explain")
    assert llm.requests[0].extensions["timeout"]["read"] > 29.0


async def test_no_time_left_makes_no_call(llm: Harness) -> None:
    await _fails_with(llm.client(llm_timeout_s=0.0), ErrorCode.LLM_TIMEOUT)
    assert llm.requests == []


@pytest.mark.parametrize("missing", ["groq_api_key", "groq_model"])
async def test_missing_settings_make_no_call(llm: Harness, missing: str) -> None:
    await _fails_with(llm.client(**{missing: ""}), ErrorCode.LLM_UNAVAILABLE)
    assert llm.requests == []


# --- llm_calls rows (Design.md §4.8, §5)


async def test_success_writes_one_row(llm: Harness) -> None:
    async with llm.sessions() as db:
        user = User(
            email="a@example.com",
            password_hash="x",
            display_name="a",
            consent_at=utcnow(),
        )
        db.add(user)
        await db.commit()
        user_id = user.id
    token = request_id_var.set("req-1")
    try:
        llm.script = [ok(prompt=12, completion=3)]
        await llm.client().complete(messages=MESSAGES, task="explain", user_id=user_id)
    finally:
        request_id_var.reset(token)

    [row] = await llm.rows()
    assert row.request_id == "req-1"
    assert row.user_id == user_id
    assert row.task == "explain"
    assert row.model == MAIN
    assert row.prompt_tokens == 12
    assert row.completion_tokens == 3
    assert row.outcome == "ok"
    assert row.fallback_used is False
    assert row.latency_ms >= 0


async def test_every_attempt_writes_its_own_row(llm: Harness) -> None:
    # The dashboard counts 429 responses and fallback calls from these rows (FR-43b).
    llm.script = [status(429, "1"), status(413), ok(prompt=8, completion=2)]
    await llm.client().complete(messages=MESSAGES, task="explain")
    rows = await llm.rows()
    assert [(r.model, r.outcome, r.fallback_used) for r in rows] == [
        (MAIN, "rate_limited", False),
        (MAIN, "too_large", False),
        (FALLBACK, "ok", True),
    ]
    assert [r.prompt_tokens for r in rows] == [0, 0, 8]


@pytest.mark.parametrize(
    ("failure", "outcome"),
    [
        pytest.param(lambda: httpx.ReadTimeout("slow"), "timeout", id="timeout"),
        pytest.param(lambda: status(401), "error", id="auth"),
    ],
)
async def test_failed_call_records_its_outcome(
    llm: Harness, failure: Callable[[], Any], outcome: str
) -> None:
    llm.script = [failure()]
    with pytest.raises(AppError):
        await llm.client().complete(messages=MESSAGES, task="explain")
    assert [r.outcome for r in await llm.rows()] == [outcome]


async def test_unusable_answer_is_an_error_but_its_tokens_are_counted(llm: Harness) -> None:
    # Groq counted these tokens against the daily limit even though the answer was cut off.
    llm.script = [ok("ตัดกลางค", prompt=100, completion=50, finish="length"), ok()]
    await llm.client().complete(messages=MESSAGES, task="explain")
    first = (await llm.rows())[0]
    assert (first.outcome, first.prompt_tokens, first.completion_tokens) == ("error", 100, 50)


async def test_no_prompt_or_answer_text_reaches_the_row_or_the_log(
    llm: Harness, capsys: pytest.CaptureFixture[str]
) -> None:
    llm.script = [status(500), ok("คำตอบลับ")]
    await llm.client().complete(messages=MESSAGES, task="explain")
    row = (await llm.rows())[0]
    stored = " ".join(str(v) for v in vars(row).values())
    captured = capsys.readouterr()
    for text in (stored, captured.out, captured.err):
        assert "ข้อความส่วนตัว" not in text
        assert "คำตอบลับ" not in text
        assert "test-key" not in text


async def test_logging_failure_does_not_lose_the_answer(llm: Harness) -> None:
    async with llm.engine.begin() as conn:
        await conn.run_sync(LlmCall.__table__.drop)  # type: ignore[arg-type]
    llm.script = [ok("ยังได้คำตอบ")]
    result = await llm.client().complete(messages=MESSAGES, task="explain")
    assert result.text == "ยังได้คำตอบ"
