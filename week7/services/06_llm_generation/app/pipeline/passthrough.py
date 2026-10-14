"""mode=passthrough pipeline หัวข้อ 7"""

from __future__ import annotations

import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.citations import normalize_citations
from app.config import Settings
from app.errors import AppValidationError
from app.language import language_matches, language_name
from app.llm.client import LLMClient
from app.middleware import log_event
from app.numeric_guard import (
    extract_standalone_numbers,
    find_score_claims,
    normalize_text,
)
from app.safety import gambling
from app.schemas import GenerateRequest, GenerateResponse, SafetyInfo, TokenUsage

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
)


async def run_passthrough(
    req: GenerateRequest,
    *,
    llm: LLMClient,
    settings: Settings,
    request_id: str,
) -> GenerateResponse:
    start = time.monotonic()
    language = req.language if req.language in ("th", "en") else "th"

    if not req.draft or not req.draft.strip():
        raise AppValidationError("draft ต้องไม่ว่างสำหรับ mode=passthrough")

    draft = req.draft
    model_used = "none"
    token_usage = TokenUsage()

    if language_matches(draft, language):
        answer = draft
    else:
        prompt = _env.get_template("passthrough_translate.j2").render(
            language_name=language_name(language), draft=draft
        )
        messages = [{"role": "user", "content": prompt}]
        remaining = settings.generate_deadline_s - (time.monotonic() - start)
        result = await llm.chat(
            messages,
            temperature=settings.temperature_passthrough,
            max_tokens=settings.max_output_tokens,
            deadline=remaining,
            purpose="translate",
        )
        translated = normalize_citations(result.text)

        draft_norm = normalize_text(draft)
        translated_norm = normalize_text(translated)

        # ตรวจว่าชุดตัวเลขในผลแปล = ชุดตัวเลขใน draft (จับตัวเลขทั่วไปที่หายไป/เกิน)
        draft_nums = sorted(extract_standalone_numbers(draft_norm))
        translated_nums = sorted(extract_standalone_numbers(translated_norm))

        # เดิมเช็คแค่ standalone numbers ที่ sorted() แล้ว ทำให้สกอร์ที่ "กลับด้าน"
        # เช่น 2-1 แปลผิดเป็น 1-2 (ทีมชนะ/แพ้สลับกัน) ตัวเลขหลัง sort เท่ากันทั้งคู่
        # ([1,2] == [1,2]) เช็คผ่านทั้งที่ความหมายกลับด้านสนิท — เพิ่มการเช็คสกอร์แบบ
        # รักษาลำดับ (find_score_claims คืน tuple (home, away) ไม่ sort) เพื่อจับกรณีนี้
        draft_scores = find_score_claims(draft_norm)
        translated_scores = find_score_claims(translated_norm)

        if draft_nums != translated_nums or draft_scores != translated_scores:
            log_event(
                "translate_number_mismatch",
                request_id,
                draft_scores=str(draft_scores),
                translated_scores=str(translated_scores),
            )
            answer = draft
        else:
            answer = translated
            model_used = result.model
            token_usage = TokenUsage(
                input=result.usage.input, output=result.usage.output
            )

    # safety: ในโหมดนี้ไม่มี context ให้ยกเว้น ใช้เกณฑ์เข้มกว่า grounded
    safety_blocked = False
    safety_reason = None
    reason = gambling.check_answer(answer, allow_context_odds=False)
    if reason:
        safety_blocked = True
        safety_reason = reason
        log_event(
            "safety_blocked",
            request_id,
            reason=reason,
            mode="passthrough",
            text=answer[:200],
        )
        answer = gambling.refusal_text(language)

    latency_ms = int((time.monotonic() - start) * 1000)
    return GenerateResponse(
        request_id=request_id,
        answer=answer,
        sources=[],
        citations_removed=0,
        safety=SafetyInfo(blocked=safety_blocked, reason=safety_reason),
        model=model_used,
        latency_ms=latency_ms,
        token_usage=token_usage,
    )
