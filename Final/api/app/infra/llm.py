"""Groq chat completions (Design.md §4.7): model per task, retry, fallback, one log row per call.

Quota is the caller's job, around `complete` (see services/quota_service.py). Prompts, answers and
Groq's error bodies can hold personal data, so they are never logged or stored.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.ids import request_id_var
from app.core.logging import get_logger
from app.infra.models import LlmCall

log = get_logger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_RETRY_WAIT_S = 1.0
# A longer Retry-After means a limit that will not clear in time, so go to the fallback model.
MAX_RETRY_WAIT_S = 5.0
_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)

Tier = Literal["main", "router"]


@dataclass(frozen=True, slots=True)
class LlmResult:
    text: str
    data: dict[str, Any] | None  # the parsed object when json_mode is on
    model: str
    prompt_tokens: int
    completion_tokens: int
    fallback_used: bool

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class _CallFailed(Exception):
    def __init__(
        self,
        outcome: str,
        *,
        retryable: bool = False,
        can_fall_back: bool = True,
        retry_after: float | None = None,
        status: int | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        super().__init__(outcome)
        self.outcome = outcome
        self.retryable = retryable
        self.can_fall_back = can_fall_back
        self.retry_after = retry_after
        self.status = status
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return max(float(response.headers["retry-after"]), 0.0)
    except (KeyError, ValueError):  # missing, or the HTTP-date form
        return None


def _check_status(response: httpx.Response) -> None:
    code = response.status_code
    if code == 200:
        return
    if code == 429:
        raise _CallFailed(
            "rate_limited", retryable=True, retry_after=_retry_after(response), status=code
        )
    if code == 413:
        raise _CallFailed("too_large", status=code)
    if code in (401, 403):  # the key is wrong: no other attempt can work
        raise _CallFailed("error", can_fall_back=False, status=code)
    raise _CallFailed("error", retryable=code >= 500, status=code)


def _parse_answer(response: httpx.Response, *, json_mode: bool) -> tuple[str, Any, int, int]:
    """(text, data, prompt tokens, completion tokens), or _CallFailed for an unusable answer."""
    try:
        body = response.json()
        usage = body.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        choice = body["choices"][0]
        content = choice["message"].get("content") or ""
        finish_reason = choice.get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as problem:
        raise _CallFailed("error", status=response.status_code) from problem

    # Failed answers keep their tokens: Groq counted them against the daily limit.
    spent = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    if not isinstance(content, str):
        raise _CallFailed("error", status=response.status_code, **spent)
    text = _THINKING.sub("", content).strip()
    # A reasoning model can spend every token on thinking, which ends as "length".
    if not text or finish_reason == "length":
        raise _CallFailed("error", status=response.status_code, **spent)
    data = None
    if json_mode:
        try:
            data = json.loads(text)
        except ValueError as problem:
            raise _CallFailed("error", status=response.status_code, **spent) from problem
        if not isinstance(data, dict):
            raise _CallFailed("error", status=response.status_code, **spent)
    return text, data, prompt_tokens, completion_tokens


class GroqClient:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._sleep = sleep
        self._http = httpx.AsyncClient(transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        task: str,
        tier: Tier = "main",
        user_id: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> LlmResult:
        """One answer, or AppError(LLM_UNAVAILABLE / LLM_TIMEOUT).

        429 and server errors: wait, retry once, then one call to the fallback model.
        413 and unusable answers: straight to the fallback model.
        `LLM_TIMEOUT_S` covers all attempts together. On the main model a timeout ends the call,
        because a long answer can use all of that time. Router-tier answers are short and normally
        take under 1 s, so each attempt gets `LLM_ROUTER_ATTEMPT_TIMEOUT_S`, and a timeout is
        retried at once like a server error. With `json_mode`, a message must say "JSON" (Groq
        requires it) and `result.data` holds the parsed object.
        """
        settings = self._settings
        model = settings.groq_router_model if tier == "router" else settings.groq_model
        if not settings.groq_api_key or not model:
            log.warning("llm_not_configured", task=task)
            raise AppError(ErrorCode.LLM_UNAVAILABLE)

        deadline = time.monotonic() + settings.llm_timeout_s
        attempt_limit = settings.llm_router_attempt_timeout_s if tier == "router" else None

        async def attempt(attempt_model: str, *, fallback_used: bool = False) -> LlmResult:
            return await self._attempt(
                attempt_model,
                fallback_used=fallback_used,
                deadline=deadline,
                attempt_limit=attempt_limit,
                messages=messages,
                task=task,
                user_id=user_id,
                json_mode=json_mode,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        try:
            try:
                return await attempt(model)
            except _CallFailed as failed:
                wait = await self._retry_wait(failed, deadline)
                if wait is None:
                    raise
                await self._sleep(wait)
                return await attempt(model)
        except _CallFailed as failed:
            fallback = settings.groq_fallback_model
            if failed.can_fall_back and fallback not in ("", model):
                try:
                    return await attempt(fallback, fallback_used=True)
                except _CallFailed as last:
                    raise self._to_app_error(last) from last
            raise self._to_app_error(failed) from failed

    @staticmethod
    async def _retry_wait(failed: _CallFailed, deadline: float) -> float | None:
        if not failed.retryable:
            return None
        wait = DEFAULT_RETRY_WAIT_S if failed.retry_after is None else failed.retry_after
        if wait > MAX_RETRY_WAIT_S or wait >= deadline - time.monotonic():
            return None
        return wait

    @staticmethod
    def _to_app_error(failed: _CallFailed) -> AppError:
        code = ErrorCode.LLM_TIMEOUT if failed.outcome == "timeout" else ErrorCode.LLM_UNAVAILABLE
        return AppError(code)

    async def _attempt(
        self,
        model: str,
        *,
        fallback_used: bool,
        deadline: float,
        attempt_limit: float | None,
        messages: list[dict[str, str]],
        task: str,
        user_id: str | None,
        json_mode: bool,
        max_tokens: int,
        temperature: float,
    ) -> LlmResult:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _CallFailed("timeout", can_fall_back=False)

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if model.startswith("openai/gpt-oss"):
            body["include_reasoning"] = False
            body["reasoning_effort"] = "low"  # thinking uses up the 8K tokens/min

        # Set only when time would be left afterwards for another attempt.
        limited = attempt_limit if attempt_limit is not None and attempt_limit < remaining else None
        started = time.perf_counter()
        outcome, prompt_tokens, completion_tokens = "error", 0, 0
        try:
            try:
                response = await self._http.post(
                    GROQ_CHAT_URL,
                    json=body,
                    headers={"Authorization": f"Bearer {self._settings.groq_api_key}"},
                    timeout=remaining if limited is None else limited,
                )
            except httpx.TimeoutException as problem:
                # Connect, read or pool: says where a stuck call was, which the cause depends on.
                log.warning("llm_call_timed_out", task=task, kind=type(problem).__name__)
                if limited is None:
                    raise _CallFailed("timeout", can_fall_back=False) from problem
                raise _CallFailed("timeout", retryable=True, retry_after=0.0) from problem
            except httpx.HTTPError as problem:
                raise _CallFailed("error", retryable=True) from problem
            _check_status(response)
            text, data, prompt_tokens, completion_tokens = _parse_answer(
                response, json_mode=json_mode
            )
            outcome = "ok"
        except _CallFailed as failed:
            outcome = failed.outcome
            prompt_tokens, completion_tokens = failed.prompt_tokens, failed.completion_tokens
            log.warning(
                "llm_call_failed", task=task, model=model, outcome=outcome, status=failed.status
            )
            raise
        finally:
            await self._record(
                task=task,
                model=model,
                user_id=user_id,
                outcome=outcome,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=round((time.perf_counter() - started) * 1000),
                fallback_used=fallback_used,
            )
        return LlmResult(
            text=text,
            data=data,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            fallback_used=fallback_used,
        )

    async def _record(self, **fields: Any) -> None:
        try:
            async with self._sessions() as db:
                db.add(LlmCall(request_id=request_id_var.get(), **fields))
                await db.commit()
        except Exception as problem:  # the dashboard must never cost the user their answer
            log.warning("llm_call_log_failed", error_type=type(problem).__name__)
