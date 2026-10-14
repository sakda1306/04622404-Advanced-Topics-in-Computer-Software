"""
เรียก LLM ผ่านไลบรารี `openai` ตัวเดียว สลับเจ้าด้วย base_url (CONTRACT.md §8)
ลำดับ: Groq (หลัก) → error/429/timeout/response ผิดปกติ → Gemini (สำรอง) 1 ครั้ง → ล่มทั้งคู่ → LLMUnavailableError (ให้ router 503)
"""
import logging
import threading
import time

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from .config import settings

logger = logging.getLogger("engines")


class LLMUnavailableError(Exception):
    """ทั้ง Groq และ Gemini เรียกไม่สำเร็จ — main.py แปลงเป็น 503 LLM_UNAVAILABLE"""


class AnswerTooLongError(LLMUnavailableError):
    """
    [ข้อ 4] ทั้ง Groq และ Gemini เรียกสำเร็จ (provider ปกติดี) แต่ทุกครั้งตอบยาวเกิน max_tokens
    (finish_reason == "length") — สาเหตุคือ token budget ไม่พอ ไม่ใช่ provider ล่ม
    main.py ควรแยกเคสนี้ออกจาก LLM_UNAVAILABLE ทั่วไป เพราะข้อความ "ทั้ง Groq และ Gemini
    เรียกไม่สำเร็จ" ทำให้เข้าใจผิดว่า provider พัง ทั้งที่จริงคำถามแค่ต้องการคำตอบยาวกว่าที่ตั้งไว้
    ยังเป็น subclass ของ LLMUnavailableError อยู่ เพื่อให้ except LLMUnavailableError เดิมใน
    main.py ยังจับได้เหมือนเดิมโดยไม่ต้องแก้ทุกจุดที่เรียก — main.py แค่เช็ค isinstance เพิ่มถ้าอยากตอบ
    error message ที่ตรงสาเหตุกว่า
    """


class ProviderResponseInvalid(Exception):
    """
    Provider ตอบ 200 แต่ใช้งานไม่ได้จริง — เช่น content ว่าง, finish_reason == 'length'
    (โมเดล reasoning ใช้ token คิดหมดก่อนตอบ), หรือ choices ว่าง/ผิดรูป
    ถือว่าเป็นความล้มเหลวแบบเดียวกับ timeout/429 เพื่อให้ไป fallback ต่อ ไม่ใช่ตอบ 200 เปล่า ๆ

    [ข้อ 3+4] มี reason แยกกรณี "length" (ตัดกลางคันเพราะ max_tokens ไม่พอ — ไม่ใช่ provider
    พัง) ออกจาก "malformed" (response รูปแบบผิดจริง ๆ) เพื่อให้ call_general_ai รู้ว่าจะลอง
    ลด reasoning_effort ก่อน fallback ดีไหม และเพื่อให้ main.py ตอบ error ที่ตรงสาเหตุกว่าเดิม
    """

    def __init__(self, message: str, *, reason: str = "malformed"):
        super().__init__(message)
        self.reason = reason  # "length" | "malformed"


def _client(base_url: str, api_key: str) -> OpenAI:
    # [ข้อ 1] max_retries=0: ปิด retry อัตโนมัติของ SDK (ค่าเริ่มต้นคือ 2 ครั้ง + backoff)
    # เพราะ retry ในตัว client ทำให้ fallback ไป Gemini ช้าเกินงบ 25s ของ router
    # การ retry/fallback ทั้งหมดคุมเองที่ call_general_ai ชั้นเดียวพอ
    return OpenAI(base_url=base_url, api_key=api_key or "missing-key", max_retries=0)


# connect timeout สูงสุดต่อครั้ง — กัน connect ช้ากินงบไปก่อนที่จะได้เริ่มรอคำตอบ
CONNECT_TIMEOUT_SECONDS = 2.0
# ถ้างบเวลารวมเหลือน้อยกว่านี้ ไม่คุ้มที่จะเรียก provider ถัดไป
MIN_REMAINING_SECONDS = 1.0


def _close_client_in_background(client) -> None:
    """ปิด client แบบ best effort ในเธรดแยก (daemon) โดยไม่รอผล — ผู้เรียกไม่ถูกบล็อกถ้า close() ช้า"""
    close = getattr(client, "close", None)
    if not callable(close):
        return

    def _close() -> None:
        try:
            close()
        except Exception:  # noqa: BLE001 — ปิดไม่สำเร็จก็ไม่เป็นไร เพราะ raise timeout ต่ออยู่แล้ว
            pass

    threading.Thread(target=_close, name="llm-close", daemon=True).start()


def _call_with_hard_timeout(client: OpenAI, base_url: str, hard_timeout: float, **create_kwargs):
    """
    [รีวิว PR #21 รอบ 2] เพดานเวลา wall-clock จริงของ 1 hop
    httpx.Timeout จำกัดแยกรายช่วง (connect/read/write/pool) และ read timeout นับต่อการรอ chunk
    ไม่ใช่เวลารวมของคำขอ จึงรัน create() ใน daemon thread แล้วรอด้วย Event.wait(hard_timeout)
    ถ้าเกินเวลา: สั่งปิด client เพื่อตัด connection ที่ค้าง (best effort, ทำใน daemon thread ไม่รอผล) แล้วโยน APITimeoutError
    ให้ไหลเข้าเส้นทาง retryable/fallback เดิม — ผู้เรียกได้ control กลับตามเวลาเสมอ
    ผลของ thread ที่ตามมาทีหลังจะถูกทิ้ง (daemon จึงไม่ค้าง process ตอนปิดเซอร์วิส)
    """
    if hard_timeout <= 0:
        raise APITimeoutError(request=httpx.Request("POST", base_url))

    box: dict = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            box["resp"] = client.chat.completions.create(**create_kwargs)
        except BaseException as e:  # noqa: BLE001 — ส่งต่อให้ thread หลัก raise ซ้ำ
            box["err"] = e
        finally:
            done.set()

    threading.Thread(target=_worker, name="llm-call", daemon=True).start()

    if not done.wait(hard_timeout):
        # [รีวิว PR #21 รอบ 3] close() อาจบล็อก จึงไม่เรียกบนเธรดที่ตอบคำขอ — ส่งไปทำใน daemon thread
        # แล้วโยน timeout ทันที เพดาน wall-clock จะได้ไม่ถูกลากยาวด้วยขั้น cleanup
        _close_client_in_background(client)
        raise APITimeoutError(request=httpx.Request("POST", base_url))

    if "err" in box:
        raise box["err"]
    return box["resp"]


def _supports_reasoning_effort(provider: str, model: str) -> bool:
    """
    [รีวิว PR #21] reasoning_effort ส่งเฉพาะ provider+model ที่รู้ว่ารับจริง (Groq + gpt-oss)
    ไม่ส่งให้ Gemini หรือโมเดลที่ไม่ใช่ reasoning เพราะ endpoint แบบ OpenAI-compatible
    อาจตอบ 400 แทนที่จะเมิน field แปลก ๆ ซึ่งจะทำให้ fallback พังตามไปด้วย
    ถ้าเปลี่ยน GROQ_MODEL เป็นโมเดลที่ไม่มี reasoning ฟังก์ชันนี้จะคืน False เอง
    """
    return provider == "groq" and "gpt-oss" in model.lower()


def _try_provider(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    messages: list[dict],
    max_tokens: int,
    request_id: str,
    reasoning_effort: str | None = None,
) -> tuple[str, str, dict]:
    """คืน (content, model, token_usage_dict) หรือ raise ให้ผู้เรียกไปลอง provider ถัดไป"""
    client = _client(base_url, api_key)

    # [ข้อ 3+4] reasoning_effort: ลดจำนวน token ที่โมเดล reasoning (เช่น gpt-oss-120b บน Groq)
    # ใช้ "คิด" ก่อนตอบ เพื่อเหลือ token ในงบ max_tokens ให้คำตอบจริงมากขึ้น โดยไม่ต้องขยับ
    # max_tokens/GENERAL_MAX_TOKENS เอง — SDK เวอร์ชันที่ pin ไว้ (openai==1.51.0) ยังไม่มี
    # พารามิเตอร์นี้ตรง ๆ จึงส่งผ่าน extra_body (Groq รับ "reasoning_effort" เป็นฟิลด์บน request
    # body ของโมเดลตระกูล gpt-oss)
    # [รีวิว PR #21] ส่งเฉพาะ provider/model ที่รองรับ (ดู _supports_reasoning_effort) — ไม่ส่งให้
    # Gemini เพราะยังไม่ยืนยันว่า endpoint ของ Gemini เมิน field นี้หรือตอบ 400
    extra_body = (
        {"reasoning_effort": reasoning_effort}
        if reasoning_effort and _supports_reasoning_effort(provider, model)
        else None
    )

    t0 = time.monotonic()
    resp = _call_with_hard_timeout(
        client,
        base_url,
        timeout,  # เพดาน wall-clock ของ hop นี้ (ผู้เรียกส่ง min(ค่าของ provider, เวลาที่เหลือ) มาแล้ว)
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=settings.GENERAL_TEMPERATURE,
        # httpx.Timeout ยังตั้งไว้เป็นชั้นแรก (ตัด connect/read ที่ค้างเร็ว) แต่ไม่ใช่เพดานรวม —
        # เพดานรวมคือ _call_with_hard_timeout ด้านบน
        timeout=httpx.Timeout(timeout, connect=min(CONNECT_TIMEOUT_SECONDS, timeout)),
        extra_body=extra_body,
    )
    ms = int((time.monotonic() - t0) * 1000)

    # [ข้อ 3] ครอบการอ่าน choices/message ด้วย try/except แทนที่จะปล่อยให้
    # IndexError/TypeError หลุดไปถึง handler กลาง (500 โดยไม่ได้ลอง Gemini)
    try:
        choice_obj = resp.choices[0]
        content = choice_obj.message.content
        finish_reason = choice_obj.finish_reason
    except (IndexError, TypeError, AttributeError) as e:
        raise ProviderResponseInvalid(
            f"{provider} ตอบรูปแบบผิดปกติ (choices ว่าง/ไม่มี message): {e}",
            reason="malformed",
        ) from e

    # [ข้อ 2] content ว่าง หรือ finish_reason == "length" (โมเดล reasoning ใช้ token
    # คิดหมดใน max_tokens ก่อนได้คำตอบ) ถือเป็นความล้มเหลว ไม่ใช่คำตอบสำเร็จที่ตอบ 200 ด้วย content=""
    if not content or finish_reason == "length":
        raise ProviderResponseInvalid(
            f"{provider} ตอบ content ว่างหรือถูกตัดกลางคัน (finish_reason={finish_reason})",
            reason="length" if finish_reason == "length" else "malformed",
        )

    usage = resp.usage
    token_usage = {
        "input": getattr(usage, "prompt_tokens", 0) or 0,
        "output": getattr(usage, "completion_tokens", 0) or 0,
    }
    logger.info(
        '{"event":"llm_call_ok","provider":"%s","model":"%s","ms":%d,"request_id":"%s"}',
        provider,
        model,
        ms,
        request_id,
    )
    return content, model, token_usage


def call_general_ai(
    *, messages: list[dict], max_tokens: int, request_id: str, reasoning_effort: str | None = None
) -> tuple[str, str, dict]:
    """
    ลอง Groq ก่อน ถ้า error / 429 / timeout / response ใช้งานไม่ได้ ค่อยลอง Gemini หนึ่งครั้ง
    ทั้งคู่ล่ม -> LLMUnavailableError (หรือ AnswerTooLongError ถ้าล่มเพราะ "length" ล้วน ๆ)

    reasoning_effort: ส่งต่อเฉพาะ provider/model ที่รองรับ (Groq gpt-oss) — Gemini ไม่ได้รับ (ใช้ตอนที่รู้ล่วงหน้าว่าอยากได้คำตอบสั้น
    เช่น eval/llm_classifier.py ที่ต้องการแค่ JSON บรรทัดเดียว) ปล่อยเป็น None ตามปกติสำหรับ /general

    [ข้อ 4] ถ้า Groq ตอบครั้งแรกแล้วโดนตัดเพราะ "length" (ไม่ใช่ error/timeout จริง) จะลอง Groq
    ซ้ำอีกครั้งด้วย reasoning_effort="low" ก่อน ค่อย fallback ไป Gemini — ลดโอกาสเจอ 503 ปลอม ๆ
    ที่เกิดจาก token budget ไม่พอ โดยไม่ต้องขยับ GENERAL_MAX_TOKENS เอง (ข้ามขั้นนี้ถ้าผู้เรียก
    ตั้ง reasoning_effort มาเองอยู่แล้ว เพื่อไม่ให้ลองซ้ำด้วยค่าเดิม)
    """
    retryable = (
        APITimeoutError,
        RateLimitError,
        APIConnectionError,
        APIStatusError,
        ProviderResponseInvalid,  # [ข้อ 2+3] รวม response ผิดปกติเข้ากลุ่มที่ trigger fallback ด้วย
    )

    def _reason(err: Exception) -> str | None:
        return getattr(err, "reason", None)

    # [รีวิว PR #21] deadline รวมข้ามทุก hop (groq, groq low-effort retry, gemini) เท่ากับงบที่
    # config.py assert ไว้ (ROUTER_TIMEOUT - TIMEOUT_SAFETY_MARGIN) แต่ละ hop ได้ timeout =
    # min(ค่าของ provider, เวลาที่เหลือ) งบรวมจึงคุมได้จริง ไม่ใช่แค่ผลบวกของ timeout รายช่วง
    deadline = (
        time.monotonic()
        + settings.ROUTER_TIMEOUT_SECONDS
        - settings.TIMEOUT_SAFETY_MARGIN_SECONDS
    )

    def _remaining() -> float:
        return deadline - time.monotonic()

    try:
        return _try_provider(
            provider="groq",
            base_url=settings.GROQ_BASE_URL,
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            timeout=min(settings.PRIMARY_TIMEOUT_SECONDS, _remaining()),
            messages=messages,
            max_tokens=max_tokens,
            request_id=request_id,
            reasoning_effort=reasoning_effort,
        )
    except retryable as primary_err:
        logger.warning(
            '{"event":"llm_call_fallback","provider":"groq","error":"%s","request_id":"%s"}',
            str(primary_err),
            request_id,
        )

        # [ข้อ 4] เจอ length ตั้งแต่ครั้งแรกและยังไม่เคยลด reasoning_effort มาก่อน -> ลอง Groq
        # อีกรอบแบบ "คิดน้อยลง" ก่อนจะเสียเวลาไป Gemini
        # [รีวิว PR #21] ลองซ้ำเฉพาะเมื่อ Groq model รองรับ reasoning_effort จริง และเหลือเวลาพอ
        # ไม่งั้นจะเป็นการเรียกซ้ำด้วย request เดิมเป๊ะ ๆ เสียเวลาไปเปล่า
        if (
            _reason(primary_err) == "length"
            and reasoning_effort is None
            and _supports_reasoning_effort("groq", settings.GROQ_MODEL)
            and _remaining() > MIN_REMAINING_SECONDS
        ):
            try:
                return _try_provider(
                    provider="groq",
                    base_url=settings.GROQ_BASE_URL,
                    api_key=settings.GROQ_API_KEY,
                    model=settings.GROQ_MODEL,
                    timeout=min(settings.PRIMARY_TIMEOUT_SECONDS, _remaining()),
                    messages=messages,
                    max_tokens=max_tokens,
                    request_id=request_id,
                    reasoning_effort="low",
                )
            except retryable as retry_err:
                logger.warning(
                    '{"event":"llm_call_fallback","provider":"groq_low_effort",'
                    '"error":"%s","request_id":"%s"}',
                    str(retry_err),
                    request_id,
                )
                primary_err = retry_err  # ใช้ตัวหลังสุดตัดสิน reason ตอนสร้าง error รวมท้ายสุด

        # [รีวิว PR #21] งบรวมหมดแล้ว ไม่เรียก Gemini ต่อ เพราะ router จะ timeout ไปก่อนอยู่ดี
        if _remaining() < MIN_REMAINING_SECONDS:
            raise LLMUnavailableError(
                f"groq: {primary_err} | gemini: ข้าม — งบเวลารวมหมดแล้ว"
            ) from primary_err

        try:
            return _try_provider(
                provider="gemini",
                base_url=settings.GEMINI_BASE_URL,
                api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_MODEL,
                timeout=min(settings.FALLBACK_TIMEOUT_SECONDS, _remaining()),
                messages=messages,
                max_tokens=max_tokens,
                request_id=request_id,
                reasoning_effort=reasoning_effort,
            )
        except retryable as fallback_err:
            logger.error(
                '{"event":"llm_call_failed","provider":"gemini","error":"%s","request_id":"%s"}',
                str(fallback_err),
                request_id,
            )
            combined_msg = f"groq: {primary_err} | gemini: {fallback_err}"
            # [ข้อ 4] ทั้งสองรอบล่มเพราะ "length" ล้วน ๆ (ไม่ใช่ provider พัง) -> แยก error type
            # ให้ main.py ตอบสาเหตุที่ตรงกว่าเดิมได้ ไม่ปนกับ LLM_UNAVAILABLE ทั่วไป
            if _reason(primary_err) == "length" and _reason(fallback_err) == "length":
                raise AnswerTooLongError(combined_msg) from fallback_err
            raise LLMUnavailableError(combined_msg) from fallback_err