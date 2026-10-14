"""LLM client หัวข้อ 10 — ใช้ openai SDK ตัวเดียว สลับ provider ด้วย base_url

Groq = หลัก (LLM_PRIMARY), Gemini = สำรอง (LLM_FALLBACK) ผ่าน OpenAI-compatible endpoint
ห้ามลง SDK ของเจ้าอื่นเพิ่ม (google-generativeai, groq ฯลฯ)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings
from app.errors import LLMUnavailable


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str  # "groq" | "gemini"
    usage: TokenUsage
    fallback_used: bool
    latency_ms: int


class LLMClient(Protocol):
    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        deadline: float,
        purpose: str,
    ) -> LLMResult: ...


def new_canary() -> str:
    """canary token สุ่มต่อ process เพื่อตรวจ prompt leak"""
    return f"CANARY-{uuid.uuid4().hex[:12]}"


class _ProviderConfig:
    def __init__(self, name: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model


def _is_empty_content(text: str | None, finish_reason: str | None) -> bool:
    if not text or not text.strip():
        return True
    # ตัดกลางคันเพราะ token limit (finish_reason == "length") ถือว่าใช้ไม่ได้เสมอ
    # ต้อง fallback แม้จะมีข้อความบางส่วนติดมาด้วยก็ตาม
    # เดิม `finish_reason == "length" and not text.strip()` ผิด: ถ้ามาถึงบรรทัดนี้
    # ได้ text.strip() ไม่ว่างแน่นอนแล้ว (เช็คผ่านบรรทัดบนไปแล้ว) เงื่อนไขนี้จึงเป็น
    # False เสมอไม่ว่ากรณีไหน ทำให้คำตอบที่ถูกตัดกลางคันหลุดผ่านเป็น "สำเร็จ" โดยไม่
    # ลอง fallback ไปยัง provider สำรองเลย
    return finish_reason == "length"


class RealLLMClient:
    """เรียกหลัก 1 ครั้ง (ไม่ retry) → ถ้าล้มเหลว เรียกสำรอง 1 ครั้ง → ล่มทั้งคู่ raise LLMUnavailable

    ใช้ client instance เดียวต่อ provider ตลอดอายุ RealLLMClient (แชร์ connection pool
    ของ httpx ใต้ AsyncOpenAI) แทนที่จะสร้างใหม่ทุกครั้งเหมือนเดิม ซึ่งทำให้ connection
    ค้างจน GC มาเก็บ เสี่ยง socket leak เมื่อโหลดสูง — ใช้ `.with_options(timeout=...)`
    ของ openai SDK เพื่อคุม timeout ต่อ call แม่นยำเหมือนเดิม โดยยังแชร์ connection
    pool เดียวกันอยู่ (with_options คืน client ใหม่แบบ shallow copy ไม่สร้าง
    httpx transport ใหม่)
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        providers = {
            "groq": _ProviderConfig(
                "groq",
                settings.groq_api_key,
                settings.groq_base_url,
                settings.groq_model,
            ),
            "gemini": _ProviderConfig(
                "gemini",
                settings.gemini_api_key,
                settings.gemini_base_url,
                settings.gemini_model,
            ),
        }
        self._primary = providers[settings.llm_primary]
        self._fallback = providers[settings.llm_fallback]
        self._base_clients: dict[str, AsyncOpenAI] = {}

    def _base_client_for(self, provider: _ProviderConfig) -> AsyncOpenAI:
        if provider.name not in self._base_clients:
            self._base_clients[provider.name] = AsyncOpenAI(
                base_url=provider.base_url,
                api_key=provider.api_key or "unset",
                max_retries=0,  # สำคัญมาก กัน SDK retry เองแล้วกิน deadline
            )
        return self._base_clients[provider.name]

    def _client_for(self, provider: _ProviderConfig, timeout: float) -> AsyncOpenAI:
        base = self._base_client_for(provider)
        return base.with_options(timeout=timeout)

    async def aclose(self) -> None:
        """ปิด connection pool ของทุก provider ที่เคยสร้าง client ไว้ — เรียกตอน
        app shutdown (ดู lifespan ใน main.py) กัน connection ค้างเมื่อ service หยุด
        """
        for client in self._base_clients.values():
            await client.close()

    async def _call_once(
        self,
        provider: _ProviderConfig,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> tuple[str, TokenUsage]:
        client = self._client_for(provider, timeout)
        kwargs: dict = {
            "model": provider.model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        # reasoning_effort เฉพาะโมเดล openai/gpt-oss* บน Groq เท่านั้น ห้ามส่งให้ Gemini
        if provider.name == "groq" and provider.model.startswith("openai/gpt-oss"):
            kwargs["extra_body"] = {
                "reasoning_effort": self.settings.reasoning_effort,
                "include_reasoning": False,
            }
        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        content = choice.message.content or ""
        finish_reason = choice.finish_reason
        usage = TokenUsage(
            input=getattr(resp.usage, "prompt_tokens", 0) or 0,
            output=getattr(resp.usage, "completion_tokens", 0) or 0,
        )
        if _is_empty_content(content, finish_reason):
            raise RuntimeError(
                f"empty content from {provider.name} (finish_reason={finish_reason})"
            )
        return content, usage

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        deadline: float,
        purpose: str,
    ) -> LLMResult:
        start = time.monotonic()
        primary_timeout = max(deadline * 0.55, 3.0)

        try:
            text, usage = await asyncio.wait_for(
                self._call_once(
                    self._primary,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=primary_timeout,
                ),
                timeout=primary_timeout,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            return LLMResult(
                text=text,
                model=self._primary.model,
                provider=self._primary.name,
                usage=usage,
                fallback_used=False,
                latency_ms=latency_ms,
            )
        except Exception:  # noqa: BLE001 — ต้อง catch ทุก error ของ provider (timeout/429/5xx/conn/parse) เพื่อ fallback
            elapsed = time.monotonic() - start
            remaining = deadline - elapsed
            if remaining < 5.0:
                raise LLMUnavailable(
                    "primary failed and not enough time left for fallback"
                )
            try:
                text, usage = await asyncio.wait_for(
                    self._call_once(
                        self._fallback,
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=remaining,
                    ),
                    timeout=remaining,
                )
                latency_ms = int((time.monotonic() - start) * 1000)
                return LLMResult(
                    text=text,
                    model=self._fallback.model,
                    provider=self._fallback.name,
                    usage=usage,
                    fallback_used=True,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                raise LLMUnavailable(
                    "both primary and fallback providers failed"
                ) from exc

    async def check_models_available(self) -> None:
        """startup check: เรียก models.list() timeout สั้น ไม่ทำให้ service ล้มถ้าพลาด"""
        for provider in (self._primary, self._fallback):
            if not provider.api_key:
                continue
            try:
                client = self._client_for(provider, timeout=5.0)
                models = await client.models.list()
                ids = {m.id for m in models.data}
                if provider.model not in ids:
                    from app.middleware import log_event

                    log_event(
                        "model_missing",
                        "-",
                        provider=provider.name,
                        model=provider.model,
                    )
            except Exception as exc:  # noqa: BLE001
                from app.middleware import log_event

                log_event(
                    "model_check_failed",
                    "-",
                    provider=provider.name,
                    error=str(exc)[:200],
                )
