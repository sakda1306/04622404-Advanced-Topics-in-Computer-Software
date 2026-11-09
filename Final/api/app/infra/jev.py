"""TypeSafe Jev choice questions (Design.md §4.6): one attempt, one log row per call.

A failed call raises JevFailed so the caller can use Groq, which is why there is no retry here.
Messages and Jev's error bodies can hold personal data, so they are never logged or stored.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.ids import request_id_var
from app.core.logging import get_logger
from app.infra.models import LlmCall

log = get_logger(__name__)

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_ROUTER_TASK = "router_jev"
JEV_WORK_STYLE_TASK = "work_style_jev"
JEV_TASKS = (JEV_ROUTER_TASK, JEV_WORK_STYLE_TASK)
_MODEL = "jev-latest"
_QUESTION = "route"


class JevFailed(Exception):
    """Jev gave no usable answer. Holds only the outcome, never any response text."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


@dataclass(frozen=True, slots=True)
class JevChoice:
    choice: str
    confidence: float


def _parse_choice(body: Any, options: dict[str, str]) -> JevChoice:
    try:
        answer = body["answers"][_QUESTION]
        choice, confidence = answer["choice"], answer["confidence"]
    except (KeyError, TypeError) as problem:
        raise JevFailed("error") from problem
    if (
        not isinstance(choice, str)
        or choice not in options
        or isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not math.isfinite(confidence)
    ):
        raise JevFailed("error")
    return JevChoice(choice=choice, confidence=min(max(float(confidence), 0.0), 1.0))


def _spent_tokens(body: Any) -> int:
    try:
        return int(body["usage"]["input_tokens"] or 0)
    except (KeyError, TypeError, ValueError):
        return 0


class JevClient:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._http = httpx.AsyncClient(transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def choose(
        self,
        *,
        state: dict[str, Any],
        instructions: str,
        options: dict[str, str],
        task: str,
        user_id: str | None = None,
    ) -> JevChoice:
        """One answer from `options`, or JevFailed."""
        started = time.perf_counter()
        outcome, model, tokens = "error", _MODEL, 0
        try:
            try:
                response = await self._http.post(
                    JEV_URL,
                    json={
                        "model": _MODEL,
                        "state": state,
                        "questions": {
                            _QUESTION: {
                                "type": "choice",
                                "instructions": instructions,
                                "criteria": options,
                            }
                        },
                    },
                    headers={"Authorization": f"Bearer {self._settings.typesafe_api_key}"},
                    timeout=self._settings.jev_timeout_s,
                )
            except httpx.TimeoutException as problem:
                raise JevFailed("timeout") from problem
            except httpx.HTTPError as problem:
                raise JevFailed("error") from problem
            if response.status_code == 429:
                raise JevFailed("rate_limited")
            if response.status_code != 200:
                log.warning("jev_call_failed", task=task, status=response.status_code)
                raise JevFailed("error")
            try:
                body = response.json()
            except ValueError as problem:
                raise JevFailed("error") from problem
            tokens = _spent_tokens(body)  # output is free, and a bad answer may still be billed
            if isinstance(body, dict) and isinstance(body.get("model"), str):
                model = body["model"]
            chosen = _parse_choice(body, options)
            outcome = "ok"
            return chosen
        except JevFailed as failed:
            outcome = failed.outcome
            raise
        finally:
            await self._record(
                task=task,
                model=model,
                user_id=user_id,
                outcome=outcome,
                prompt_tokens=tokens,
                completion_tokens=0,
                latency_ms=round((time.perf_counter() - started) * 1000),
                fallback_used=False,
            )

    async def _record(self, **fields: Any) -> None:
        try:
            async with self._sessions() as db:
                db.add(LlmCall(request_id=request_id_var.get(), **fields))
                await db.commit()
        except Exception as problem:  # the dashboard must never cost the user their answer
            log.warning("llm_call_log_failed", error_type=type(problem).__name__)


def build_jev(settings: Settings, sessions: async_sessionmaker[AsyncSession]) -> JevClient | None:
    """A client only when switched on and given a key, so Groq stays the default."""
    if not settings.jev_router_enabled or not settings.typesafe_api_key:
        return None
    return JevClient(settings, sessions)
