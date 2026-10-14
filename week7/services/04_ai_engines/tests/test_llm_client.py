from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openai import APITimeoutError

from app.llm_client import LLMUnavailableError, _call_with_hard_timeout, call_general_ai


def _fake_response(text: str, prompt_tokens: int, completion_tokens: int, finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )

def test_primary_groq_success_no_fallback_called():
    with patch("app.llm_client._client") as mock_client_factory:
        mock_client = mock_client_factory.return_value
        mock_client.chat.completions.create.return_value = _fake_response("hi", 5, 5)

        content, model, usage = call_general_ai(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            request_id="r1",
        )

    assert content == "hi"
    assert usage == {"input": 5, "output": 5}
    # เรียก client แค่ครั้งเดียว (groq เท่านั้น) เพราะสำเร็จตั้งแต่ตัวแรก
    assert mock_client_factory.call_count == 1


def test_groq_timeout_falls_back_to_gemini():
    with patch("app.llm_client._client") as mock_client_factory:
        groq_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: (_ for _ in ()).throw(
                        APITimeoutError(request=SimpleNamespace())
                    )
                )
            )
        )
        gemini_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: _fake_response("fallback answer", 8, 12)
                )
            )
        )
        mock_client_factory.side_effect = [groq_client, gemini_client]

        content, model, usage = call_general_ai(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            request_id="r2",
        )

    assert content == "fallback answer"
    assert usage == {"input": 8, "output": 12}
    assert mock_client_factory.call_count == 2


def test_both_providers_fail_raises_llm_unavailable():
    with patch("app.llm_client._client") as mock_client_factory:
        broken = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: (_ for _ in ()).throw(
                        APITimeoutError(request=SimpleNamespace())
                    )
                )
            )
        )
        mock_client_factory.side_effect = [broken, broken]

        with pytest.raises(LLMUnavailableError):
            call_general_ai(
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=100,
                request_id="r3",
            )

def test_groq_finish_reason_length_falls_back_to_gemini():
    """[ข้อ 2] Groq ตอบ content ว่าง + finish_reason='length' ต้อง fallback ไป Gemini ไม่ใช่ตอบ 200 เปล่า"""
    with patch("app.llm_client._client") as mock_client_factory:
        groq_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: _fake_response("", 300, 350, finish_reason="length")
                )
            )
        )
        gemini_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: _fake_response("คำตอบจาก Gemini", 8, 12)
                )
            )
        )
        mock_client_factory.side_effect = [groq_client, gemini_client]

        content, model, usage = call_general_ai(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=350,
            request_id="r4",
        )

    assert content == "คำตอบจาก Gemini"
    assert mock_client_factory.call_count == 2


def test_groq_empty_choices_falls_back_to_gemini():
    """[ข้อ 3] choices ว่างจาก Groq ต้องไม่โยน IndexError ออกไปถึง 500 แต่ fallback แทน"""
    with patch("app.llm_client._client") as mock_client_factory:
        broken_response = SimpleNamespace(choices=[], usage=None)
        groq_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kw: broken_response)
            )
        )
        gemini_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: _fake_response("สำรอง", 8, 12)
                )
            )
        )
        mock_client_factory.side_effect = [groq_client, gemini_client]

        content, model, usage = call_general_ai(
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=100,
            request_id="r5",
        )

    assert content == "สำรอง"
    assert mock_client_factory.call_count == 2


def test_client_created_with_max_retries_zero():
    """[ข้อ 1] ยืนยันว่า OpenAI client ถูกสร้างด้วย max_retries=0 จริง ไม่ใช้ default ของ SDK"""
    from app.llm_client import _client

    with patch("app.llm_client.OpenAI") as mock_openai_cls:
        _client("https://api.groq.com/openai/v1", "fake-key")

    _, kwargs = mock_openai_cls.call_args
    assert kwargs["max_retries"] == 0


# ---------------------------------------------------------------------------
# [รีวิว PR #21 รอบ 2] เพดานเวลา wall-clock ระหว่าง call (ไม่ใช่แค่ตรวจก่อนเริ่ม hop)
# ---------------------------------------------------------------------------
import threading
import time

from app.config import settings


def _blocking_client(release: threading.Event, started: threading.Event | None = None):
    """client ที่ create() ค้างจนกว่าจะถูกปล่อย — จำลอง provider ที่ตอบช้ากว่าเวลาคงเหลือระหว่าง call"""
    closed = threading.Event()

    def _create(**kw):
        if started is not None:
            started.set()
        release.wait(timeout=10)  # ค้างเกินเพดานของ hop แน่นอน; test จะปล่อยตอนจบเพื่อเก็บ thread
        return _fake_response("ตอบช้าเกินไป", 1, 1)

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_create)),
        close=closed.set,
    )
    return client, closed


def test_provider_hanging_mid_call_is_cut_at_deadline(monkeypatch):
    """Groq ค้างระหว่าง call: ต้องได้ control กลับตาม deadline รวม ไม่รอให้ call คืนเอง"""
    monkeypatch.setattr(settings, "ROUTER_TIMEOUT_SECONDS", 0.6)
    monkeypatch.setattr(settings, "TIMEOUT_SAFETY_MARGIN_SECONDS", 0.0)
    monkeypatch.setattr(settings, "PRIMARY_TIMEOUT_SECONDS", 30.0)  # timeout ราย provider ยาวกว่า deadline มาก
    monkeypatch.setattr(settings, "FALLBACK_TIMEOUT_SECONDS", 30.0)

    release = threading.Event()
    groq_client, groq_closed = _blocking_client(release)
    try:
        with patch("app.llm_client._client") as factory:
            factory.side_effect = [groq_client]  # เหลือเวลา < MIN_REMAINING → ต้องไม่ไปเรียก Gemini
            t0 = time.monotonic()
            with pytest.raises(LLMUnavailableError):
                call_general_ai(
                    messages=[{"role": "user", "content": "hello"}],
                    max_tokens=100,
                    request_id="r-hang-1",
                )
            elapsed = time.monotonic() - t0
    finally:
        release.set()

    assert elapsed < 1.5, f"ควรตัดที่ ~0.6s แต่ใช้ {elapsed:.2f}s"
    assert groq_closed.is_set(), "ต้องพยายามปิด client เพื่อยกเลิกคำขอที่ค้าง"


def test_fallback_hop_hanging_mid_call_is_capped_by_remaining_budget(monkeypatch):
    """Groq ล้มเร็ว แต่ Gemini ค้างระหว่าง call: ต้องไม่เกินงบรวม แม้ FALLBACK_TIMEOUT ยาวกว่า"""
    monkeypatch.setattr(settings, "ROUTER_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "TIMEOUT_SAFETY_MARGIN_SECONDS", 0.0)
    monkeypatch.setattr(settings, "PRIMARY_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr(settings, "FALLBACK_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr("app.llm_client.MIN_REMAINING_SECONDS", 0.05)

    groq_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kw: (_ for _ in ()).throw(APITimeoutError(request=SimpleNamespace()))
            )
        )
    )
    release = threading.Event()
    gemini_client, gemini_closed = _blocking_client(release)
    try:
        with patch("app.llm_client._client") as factory:
            factory.side_effect = [groq_client, gemini_client]
            t0 = time.monotonic()
            with pytest.raises(LLMUnavailableError):
                call_general_ai(
                    messages=[{"role": "user", "content": "hello"}],
                    max_tokens=100,
                    request_id="r-hang-2",
                )
            elapsed = time.monotonic() - t0
    finally:
        release.set()

    assert elapsed < 1.6, f"งบรวม 1.0s แต่ใช้ {elapsed:.2f}s"
    assert gemini_closed.is_set()


def test_slow_first_hop_then_fast_fallback_still_succeeds(monkeypatch):
    """Groq ค้างจนโดนตัดที่ timeout ของ provider แล้ว Gemini ยังตอบทันในงบที่เหลือ"""
    monkeypatch.setattr(settings, "ROUTER_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(settings, "TIMEOUT_SAFETY_MARGIN_SECONDS", 0.0)
    monkeypatch.setattr(settings, "PRIMARY_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(settings, "FALLBACK_TIMEOUT_SECONDS", 2.0)

    release = threading.Event()
    groq_client, _ = _blocking_client(release)
    gemini_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kw: _fake_response("สำรองทัน", 2, 3))
        )
    )
    try:
        with patch("app.llm_client._client") as factory:
            factory.side_effect = [groq_client, gemini_client]
            content, _model, usage = call_general_ai(
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=100,
                request_id="r-hang-3",
            )
    finally:
        release.set()

    assert content == "สำรองทัน"
    assert usage == {"input": 2, "output": 3}


def test_slow_close_does_not_block_deadline():
    """[รีวิว PR #21 รอบ 3] close() ช้า (0.4s) ต้องไม่ลาก wall-clock เกิน hard_timeout — cleanup ทำเบื้องหลัง"""
    release = threading.Event()
    close_started = threading.Event()
    close_finished = threading.Event()

    def _slow_close():
        close_started.set()
        time.sleep(0.4)
        close_finished.set()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: release.wait(timeout=10))),
        close=_slow_close,
    )
    try:
        t0 = time.monotonic()
        with pytest.raises(APITimeoutError):
            _call_with_hard_timeout(client, "https://example.test", 0.05)
        elapsed = time.monotonic() - t0

        assert elapsed < 0.25, f"hard_timeout=0.05s แต่ใช้ {elapsed:.3f}s (close() ช้าไม่ควรบล็อกผู้เรียก)"
        # cleanup ยังต้องถูกเรียกจริง (เบื้องหลัง) ไม่ใช่ถูกข้าม
        assert close_started.wait(timeout=1.0), "ต้องยังสั่ง close() ตามเดิม"
        assert close_finished.wait(timeout=2.0)
    finally:
        release.set()


def test_close_raising_is_swallowed_and_timeout_still_raised():
    release = threading.Event()

    def _bad_close():
        raise RuntimeError("close failed")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: release.wait(timeout=10))),
        close=_bad_close,
    )
    try:
        with pytest.raises(APITimeoutError):
            _call_with_hard_timeout(client, "https://example.test", 0.05)
    finally:
        release.set()