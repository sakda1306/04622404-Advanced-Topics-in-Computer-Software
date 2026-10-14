"""mode=grounded pipeline หัวข้อ 6: validate → safety → context → prompt → LLM
→ citations → numeric guard → safety → sources → response
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.citations import (
    extract_cited_refs,
    normalize_citations,
    strip_all_citations,
    strip_invalid_citations,
)
from app.config import Settings
from app.errors import AppValidationError, LLMUnavailable
from app.llm.client import LLMClient, new_canary
from app.middleware import log_event
from app.numeric_guard import check_score_mismatch, find_score_claims
from app.safety import gambling, injection
from app.schemas import (
    GenerateRequest,
    GenerateResponse,
    SafetyInfo,
    Source,
    TokenUsage,
)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
)

INSUFFICIENT_TH = "ไม่พบข้อมูลที่เพียงพอในคลังข้อมูลเพื่อตอบคำถามนี้"
INSUFFICIENT_EN = (
    "I couldn't find enough information in the knowledge base to answer this."
)

# ข้อความปฏิเสธเมื่อเจอ prompt injection ใน context ก่อนเรียก LLM
# (แยกจาก gambling.refusal_text เพราะเป็นเหตุผลคนละประเภท ให้ reviewer/log แยกแยะได้ง่าย)
INJECTION_REFUSAL_TH = (
    "ไม่สามารถประมวลผลคำขอนี้ได้ เนื่องจากตรวจพบคำสั่งที่ไม่เหมาะสมแฝงอยู่ในข้อมูลอ้างอิง"
)
INJECTION_REFUSAL_EN = "This request cannot be processed because a prompt injection attempt was detected in the reference data."

_INJECTION_DELIMITERS = [
    "<references>",
    "</references>",
    "<ref",
    "</ref>",
    "<history>",
    "</history>",
    "<question>",
    "</question>",
]


def _language_name(language: str) -> str:
    return "ไทย" if language == "th" else "English"


def _insufficient_phrase(language: str) -> str:
    return INSUFFICIENT_TH if language == "th" else INSUFFICIENT_EN


def _injection_refusal_phrase(language: str) -> str:
    return INJECTION_REFUSAL_TH if language == "th" else INJECTION_REFUSAL_EN


def _sanitize_context_text(text: str, char_limit: int) -> str:
    # ทำให้ delimiter ที่ใช้ห่อเป็นกลาง กันหลุดออกจาก context block
    for d in _INJECTION_DELIMITERS:
        text = text.replace(d, d.replace("<", "").replace(">", ""))
    # ลบ control chars
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    if len(text) > char_limit:
        text = text[:char_limit]
    return text


def _asks_top_scorer(query: str) -> bool:
    text = query.lower()
    return "ดาวซัลโว" in text or (
        any(word in text for word in ("ยิง", "ทำประตู", "goals", "scorer"))
        and any(
            word in text
            for word in (
                "เยอะสุด",
                "เยอะที่สุด",
                "มากที่สุด",
                "สูงสุด",
                "most goals",
                "top scorer",
            )
        )
        and (
            "ใคร" in text
            or "คนไหน" in text
            or re.search(r"\b(?:who|which player)\b", text)
        )
    )


def _complete_team_scope(req: GenerateRequest) -> bool:
    if len(req.scope_team_ids) != 1:
        return False
    team_id = req.scope_team_ids[0]
    if any(
        term in req.query.lower()
        for term in ("ทั้งลีก", "ทุกทีม", "ของลีก", "overall", "in the league")
    ):
        return False
    return all(
        c.source.team_ids == [team_id]
        and bool(
            re.fullmatch(rf"players-\d{{4}}-team-{team_id}", c.source.doc_id or "")
        )
        and "## Team scorer ranking" in c.text
        for c in req.contexts
    )


async def run_grounded(
    req: GenerateRequest,
    *,
    llm: LLMClient,
    settings: Settings,
    request_id: str,
) -> GenerateResponse:
    start = time.monotonic()
    language = req.language if req.language in ("th", "en") else "th"

    # 1. validate
    refs_seen: set[int] = set()
    for c in req.contexts:
        if c.ref in refs_seen:
            raise AppValidationError(f"contexts[].ref ซ้ำ: {c.ref}")
        refs_seen.add(c.ref)
    if not req.query.strip():
        raise AppValidationError("query ต้องไม่ว่างสำหรับ mode=grounded")

    # 2. pre-safety บน query
    reason = gambling.check_query(req.query)
    if reason:
        log_event(
            "safety_blocked",
            request_id,
            reason=reason,
            mode="grounded",
            text=req.query[:200],
        )
        return GenerateResponse(
            request_id=request_id,
            answer=gambling.refusal_text(language),
            sources=[],
            citations_removed=0,
            safety=SafetyInfo(blocked=True, reason=reason),
            model="none",
            latency_ms=int((time.monotonic() - start) * 1000),
            token_usage=TokenUsage(),
        )

    # 3. contexts ว่าง → ไม่เรียก LLM
    if not req.contexts:
        return GenerateResponse(
            request_id=request_id,
            answer=_insufficient_phrase(language),
            sources=[],
            citations_removed=0,
            safety=SafetyInfo(blocked=False, reason=None),
            model="none",
            latency_ms=int((time.monotonic() - start) * 1000),
            token_usage=TokenUsage(),
        )

    # 4. เตรียม context: sanitize + injection detection + token budget
    sanitized_contexts = []
    known_scores: set[tuple[int, int]] = set()
    injection_detected = False
    injection_refs: list[int] = []
    for c in req.contexts:
        clean_text = _sanitize_context_text(c.text, settings.context_char_limit)
        if injection.detect_injection(clean_text):
            injection_detected = True
            injection_refs.append(c.ref)
            log_event(
                "injection_suspected", request_id, ref=c.ref, doc_id=c.source.doc_id
            )
        sanitized_contexts.append((c.ref, clean_text, c.source))
        # เก็บสกอร์ "ทุกคู่" ที่ปรากฏใน chunk นี้ (ไม่ใช่แค่คู่แรก) — chunk รายงาน
        # สัปดาห์จาก 07/05 อาจมีหลายแมตช์ในก้อนเดียวกัน ใช้ตัวตรวจร่วมกับ
        # numeric_guard เพื่อกันสกอร์ปลอมจากรูปแบบเวลา/ปี/matchweek ให้สม่ำเสมอกัน
        known_scores.update(find_score_claims(clean_text))

    # 4.1 บล็อกทันทีถ้าเจอ pattern injection ใน context — ก่อนเรียก LLM
    # (เดิมพึ่งพา detect_prompt_leak ที่ post-safety อย่างเดียว ซึ่งขึ้นกับว่า
    # LLM จะ "เผลอทำตาม" คำสั่งแปลกปลอมหรือไม่ ผลเลยไม่คงเส้นคงวาระหว่าง
    # mock กับ provider จริงแต่ละตัว — บล็อกจาก pattern ใน input ตรง ๆ แทน
    # ให้ผลเหมือนกันเสมอไม่ว่าจะใช้ LLM ตัวไหน เหมือนแนวทางของ gambling.check_query)
    if injection_detected:
        log_event(
            "safety_blocked",
            request_id,
            reason="injection_attempt",
            mode="grounded",
            refs=str(injection_refs),
        )
        return GenerateResponse(
            request_id=request_id,
            answer=_injection_refusal_phrase(language),
            sources=[],
            citations_removed=0,
            safety=SafetyInfo(blocked=True, reason="injection_attempt"),
            model="none",
            latency_ms=int((time.monotonic() - start) * 1000),
            token_usage=TokenUsage(),
        )

    # Player chunks cannot establish a league-wide ranking. A query scoped to one
    # team may use that team's complete player document.
    if (
        _asks_top_scorer(req.query)
        and all(c.source.category == "player" for c in req.contexts)
        and not _complete_team_scope(req)
    ):
        log_event("ranking_context_insufficient", request_id, mode="grounded")
        return GenerateResponse(
            request_id=request_id,
            answer=_insufficient_phrase(language),
            sources=[],
            citations_removed=0,
            safety=SafetyInfo(blocked=False, reason=None),
            model="none",
            latency_ms=int((time.monotonic() - start) * 1000),
            token_usage=TokenUsage(),
        )

    # token budget: ตัด context ท้ายสุดก่อนถ้าเกิน (คง ref เดิม ห้าม renumber)
    from app.tokens import estimate_tokens

    total_tokens = sum(estimate_tokens(t) for _, t, _ in sanitized_contexts)
    trimmed = 0
    while total_tokens > settings.max_context_tokens and len(sanitized_contexts) > 1:
        removed = sanitized_contexts.pop()
        total_tokens -= estimate_tokens(removed[1])
        trimmed += 1
    if trimmed:
        log_event("contexts_trimmed", request_id, trimmed=trimmed)

    history = req.history[-6:]
    history = [type(h)(role=h.role, content=h.content[:500]) for h in history]

    canary = new_canary()
    system_prompt = _env.get_template("grounded.j2").render(
        canary=canary,
        insufficient_phrase=_insufficient_phrase(language),
        language_name=_language_name(language),
    )

    class _CtxView:
        def __init__(self, ref, text, source):
            self.ref = ref
            self.text = text
            self.source = source

    user_prompt = _env.get_template("grounded_user.j2").render(
        contexts=[_CtxView(r, t, s) for r, t, s in sanitized_contexts],
        history=history,
        query=req.query,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    deadline_remaining = settings.generate_deadline_s - (time.monotonic() - start)

    async def _call_llm(msgs, deadline):
        return await llm.chat(
            msgs,
            temperature=settings.temperature_grounded,
            max_tokens=settings.max_output_tokens,
            deadline=deadline,
            purpose="grounded",
        )

    result = await _call_llm(messages, deadline_remaining)

    total_usage = TokenUsage(input=result.usage.input, output=result.usage.output)
    answer = result.text
    model_used = result.model

    # 6.7 citations
    answer = normalize_citations(answer)
    valid_refs = {r for r, _, _ in sanitized_contexts}
    cited = extract_cited_refs(answer)
    answer, citations_removed = strip_invalid_citations(answer, valid_refs)

    is_insufficient = answer.strip().startswith((INSUFFICIENT_TH, INSUFFICIENT_EN))
    if is_insufficient:
        answer = strip_all_citations(answer)

    # 6.8 numeric guard (hard: score_mismatch, retry <=1 ถ้าเวลาเหลือ >= 8s)
    if settings.numeric_guard != "off" and not is_insufficient:
        mismatches = check_score_mismatch(answer, known_scores)
        if mismatches:
            remaining = settings.generate_deadline_s - (time.monotonic() - start)
            if settings.numeric_guard == "strict" and remaining >= 8.0:
                warn = (
                    f"\n\n[ระบบ] ตัวเลขสกอร์ {mismatches} ไม่พบตรงกันใน references "
                    "กรุณาตอบใหม่โดยใช้เฉพาะตัวเลขที่มีใน references เท่านั้น"
                )
                retry_messages = messages + [
                    {"role": "assistant", "content": result.text},
                    {"role": "user", "content": warn},
                ]
                try:
                    retry_result = await llm.chat(
                        retry_messages,
                        temperature=0.0,
                        max_tokens=settings.max_output_tokens,
                        deadline=remaining,
                        purpose="grounded",
                    )
                    total_usage.input += retry_result.usage.input
                    total_usage.output += retry_result.usage.output
                    model_used = retry_result.model
                    retry_answer = normalize_citations(retry_result.text)
                    retry_answer, extra_removed = strip_invalid_citations(
                        retry_answer, valid_refs
                    )
                    citations_removed += extra_removed
                    retry_mismatches = check_score_mismatch(retry_answer, known_scores)
                    if retry_mismatches:
                        log_event(
                            "numeric_guard_failed",
                            request_id,
                            mismatches=str(retry_mismatches),
                        )
                        answer = _insufficient_phrase(language)
                        cited = []
                    else:
                        answer = retry_answer
                        cited = extract_cited_refs(answer)
                except LLMUnavailable:
                    log_event(
                        "numeric_guard_failed", request_id, mismatches=str(mismatches)
                    )
                    answer = _insufficient_phrase(language)
                    cited = []
            elif settings.numeric_guard == "strict":
                log_event(
                    "numeric_guard_failed",
                    request_id,
                    mismatches=str(mismatches),
                    reason="no_time_for_retry",
                )
                answer = _insufficient_phrase(language)
                cited = []
            else:  # warn
                log_event(
                    "numeric_guard_mismatch", request_id, mismatches=str(mismatches)
                )

    if (
        not cited
        and not answer.strip().startswith((INSUFFICIENT_TH, INSUFFICIENT_EN))
        and req.contexts
    ):
        log_event("no_citation", request_id)

    # 9. post-safety (defense-in-depth: เช็คซ้ำแม้ผ่านขั้นตอน 4.1 มาแล้ว
    # เผื่อกรณี LLM เองสร้างเนื้อหาที่ไม่เหมาะสมขึ้นมาเอง หรือ canary หลุดจากทางอื่น)
    safety_blocked = False
    safety_reason = None
    reason = gambling.check_answer(answer, allow_context_odds=True)
    if not reason and injection.detect_prompt_leak(answer, canary):
        reason = "prompt_leak"
    if reason:
        safety_blocked = True
        safety_reason = reason
        log_event(
            "safety_blocked",
            request_id,
            reason=reason,
            mode="grounded",
            text=answer[:200],
        )
        answer = gambling.refusal_text(language)
        cited = []

    # 10. compose sources
    sources: list[Source] = []
    if not safety_blocked and not answer.strip().startswith(
        (INSUFFICIENT_TH, INSUFFICIENT_EN)
    ):
        by_ref = {r: s for r, _, s in sanitized_contexts}
        for r in sorted(set(cited)):
            if r in by_ref:
                sources.append(by_ref[r])

    latency_ms = int((time.monotonic() - start) * 1000)
    return GenerateResponse(
        request_id=request_id,
        answer=answer,
        sources=sources,
        citations_removed=citations_removed,
        safety=SafetyInfo(blocked=safety_blocked, reason=safety_reason),
        model=model_used,
        latency_ms=latency_ms,
        token_usage=total_usage,
    )
