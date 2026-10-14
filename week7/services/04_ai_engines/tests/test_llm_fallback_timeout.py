from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APITimeoutError

from app import config
from app.llm_client import AnswerTooLongError, LLMUnavailableError, call_general_ai


def _mock_response(content="ok", finish_reason="stop"):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content), finish_reason=finish_reason)]
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return resp


def _timeout_error():
    # APITimeoutError ต้องการ httpx.Request จริงตาม signature ของ openai SDK ที่ pin ไว้
    return APITimeoutError(request=httpx.Request("POST", "https://example.test/chat/completions"))


def test_fallback_timeout_budget_stays_under_router_deadline():
    """
    [รีวิว PR #21 ข้อ 1] งบเวลารวมของ Groq primary + Groq retry (low effort) + Gemini fallback
    ต้องต่ำกว่า timeout ที่ Router 03 ใช้เรียก /general (services/03_ai_router_agent/app/clients.py:59
    ตั้งไว้ 25s) พร้อมเผื่อ margin สำหรับ network/serialization overhead

    เทสนี้ตรวจ invariant ที่ config.py บังคับไว้ตอน import โดยตรง (แทนที่จะ sleep จริงตามค่า
    timeout ซึ่งจะทำให้ CI ช้าและ flaky) — ถ้าใครแก้ env จนงบเวลาเกิน assert ใน config.py
    จะ fail ทันทีตอน import อยู่แล้ว แต่เทสนี้ทำให้เห็นชัดเจนใน CI ว่ากำลังตรวจอะไร
    """
    worst_case = (
        2 * config.settings.PRIMARY_TIMEOUT_SECONDS + config.settings.FALLBACK_TIMEOUT_SECONDS
    )
    deadline_with_margin = (
        config.settings.ROUTER_TIMEOUT_SECONDS - config.settings.TIMEOUT_SAFETY_MARGIN_SECONDS
    )
    assert worst_case <= deadline_with_margin


@patch("app.llm_client._client")
def test_call_general_ai_uses_configured_timeout_for_every_hop(mock_client_factory):
    """
    จำลอง Groq รอบแรกตอบ finish_reason="length" (จุดที่ทำให้เกิดการ retry ตามที่รีวิว PR #21
    ข้อ 1 พูดถึง) แล้ว retry รอบสอง (low effort) ก็ยัง length อีก จึง fallback ไป Gemini ซึ่งตอบสำเร็จ

    หมายเหตุ: การ retry Groq ซ้ำเกิดขึ้นเฉพาะตอน reason == "length" (ProviderResponseInvalid)
    เท่านั้น — error ทั่วไปอย่าง timeout/APIConnectionError ไม่มี reason นี้ จึงข้ามไป Gemini ทันที
    โดยไม่ retry Groq ซ้ำ (ดู _reason() ใน llm_client.py) เทสนี้จึงต้อง mock ด้วย finish_reason
    ไม่ใช่ exception ทั่วไป ถึงจะเห็นครบทั้ง 3 hop

    ตรวจว่าทุก hop ถูกเรียกด้วย timeout ตาม settings จริง ไม่มี hop ไหนแอบใช้ค่า default ของ SDK
    เพราะถ้าหลุด default (เช่นไม่ส่ง timeout หรือ SDK auto-retry) จะทำให้งบเวลารวมที่คำนวณไว้ใน
    config.py ไม่ตรงกับพฤติกรรมจริง และอาจเกินงบ 25s ของ router โดยไม่มีใครรู้ตัว
    """
    groq_mock = MagicMock()
    gemini_mock = MagicMock()

    groq_mock.chat.completions.create.side_effect = [
        _mock_response("", finish_reason="length"),  # primary: ตัดกลางคัน
        _mock_response("", finish_reason="length"),  # retry (low effort): ตัดกลางคันอีกครั้ง
    ]
    gemini_mock.chat.completions.create.return_value = _mock_response("Gemini answer")

    def _client_side_effect(base_url, api_key):
        return groq_mock if base_url == config.settings.GROQ_BASE_URL else gemini_mock

    mock_client_factory.side_effect = _client_side_effect

    content, model_used, _ = call_general_ai(
        messages=[{"role": "user", "content": "สวัสดี"}],
        max_tokens=100,
        request_id="req-timeout-test",
    )

    assert content == "Gemini answer"
    # Groq ถูกเรียก 2 ครั้ง (primary + retry low-effort เพราะ reason == "length" ทั้งคู่)
    assert groq_mock.chat.completions.create.call_count == 2
    # timeout ถูกส่งเป็น httpx.Timeout (read = ค่าตาม settings, connect สั้นกว่า) — ดูรีวิว PR #21
    groq_timeouts = [
        call.kwargs["timeout"].read for call in groq_mock.chat.completions.create.call_args_list
    ]
    assert groq_timeouts == [
        config.settings.PRIMARY_TIMEOUT_SECONDS,
        config.settings.PRIMARY_TIMEOUT_SECONDS,
    ]

    gemini_timeout = gemini_mock.chat.completions.create.call_args.kwargs["timeout"]
    assert gemini_timeout.read == config.settings.FALLBACK_TIMEOUT_SECONDS
    assert gemini_timeout.connect <= 2.0


def test_generic_error_skips_groq_retry_and_goes_straight_to_gemini():
    """
    ยืนยันพฤติกรรมคู่กับเทสด้านบน: error ทั่วไปที่ไม่ใช่ finish_reason="length" (เช่น timeout จริง
    จาก network) ต้อง "ไม่" ลอง Groq ซ้ำ — เรียก Groq แค่ 1 ครั้งแล้วไป Gemini ทันที เพื่อไม่ให้
    เสียเวลาซ้ำเติมงบเวลารวมโดยไม่จำเป็น (retry มีไว้แก้ปัญหา token budget ไม่พอ ไม่ใช่ปัญหา
    provider ล่ม/ช้า)
    """
    with patch("app.llm_client._client") as mock_client_factory:
        groq_mock = MagicMock()
        gemini_mock = MagicMock()

        groq_mock.chat.completions.create.side_effect = _timeout_error()
        gemini_mock.chat.completions.create.return_value = _mock_response("Gemini answer")

        def _client_side_effect(base_url, api_key):
            return groq_mock if base_url == config.settings.GROQ_BASE_URL else gemini_mock

        mock_client_factory.side_effect = _client_side_effect

        content, _, _ = call_general_ai(
            messages=[{"role": "user", "content": "สวัสดี"}],
            max_tokens=100,
            request_id="req-plain-timeout-test",
        )

    assert content == "Gemini answer"
    assert groq_mock.chat.completions.create.call_count == 1
    assert gemini_mock.chat.completions.create.call_count == 1


@patch("app.llm_client._client")
def test_all_hops_length_raises_answer_too_long_without_extra_calls(mock_client_factory):
    """
    Groq ตอบ finish_reason="length" ทั้งรอบแรกและรอบ retry, Gemini ก็ length เหมือนกัน
    ต้องได้ AnswerTooLongError (ไม่ปนกับ LLM_UNAVAILABLE ทั่วไปในชั้น llm_client) และเรียกรวม
    แค่ 3 ครั้ง (Groq x2 + Gemini x1) — ไม่มีการวนซ้ำเกินจำนวนที่ออกแบบไว้ ซึ่งถ้าเกินจะกินเวลา
    เกินงบที่คำนวณไว้ในเทสด้านบนทันที
    """
    groq_mock = MagicMock()
    gemini_mock = MagicMock()

    groq_mock.chat.completions.create.return_value = _mock_response("", finish_reason="length")
    gemini_mock.chat.completions.create.return_value = _mock_response("", finish_reason="length")

    def _client_side_effect(base_url, api_key):
        return groq_mock if base_url == config.settings.GROQ_BASE_URL else gemini_mock

    mock_client_factory.side_effect = _client_side_effect

    with pytest.raises(AnswerTooLongError):
        call_general_ai(
            messages=[{"role": "user", "content": "สวัสดี"}],
            max_tokens=100,
            request_id="req-length-test",
        )

    assert groq_mock.chat.completions.create.call_count == 2
    assert gemini_mock.chat.completions.create.call_count == 1


def test_answer_too_long_maps_to_contract_llm_unavailable_code():
    """
    [รีวิว PR #21 ข้อ 2] CONTRACT.md §8 กำหนด code สำหรับกรณี provider ใช้ไม่ได้ไว้แค่
    LLM_UNAVAILABLE เท่านั้น — ยืนยันว่า main.py ไม่ได้ส่ง code ใหม่ (ANSWER_TOO_LONG) ที่ไม่มี
    อยู่ใน Contract ออกไปอีกต่อไป แม้สาเหตุจริงจะมาจาก AnswerTooLongError ก็ตาม
    """
    from unittest.mock import patch as _patch

    from fastapi.testclient import TestClient

    from app.llm_client import AnswerTooLongError as _AnswerTooLongError
    from app.main import app

    client = TestClient(app)

    with _patch(
        "app.main.call_general_ai",
        side_effect=_AnswerTooLongError("groq: length | gemini: length"),
    ):
        r = client.post(
            "/general",
            json={"request_id": "req-5", "query": "อธิบายยาว ๆ", "history": [], "language": "th"},
        )

    assert r.status_code == 503
    body = r.json()
    assert body["code"] == "LLM_UNAVAILABLE"
    assert "GENERAL_MAX_TOKENS" in body["detail"]


def _two_clients(groq_mock, gemini_mock):
    def _side_effect(base_url, api_key):
        return groq_mock if base_url == config.settings.GROQ_BASE_URL else gemini_mock

    return _side_effect


@patch("app.llm_client._client")
def test_reasoning_effort_sent_to_groq_gpt_oss_but_never_to_gemini(mock_client_factory):
    """
    [รีวิว PR #21] Groq (gpt-oss) ได้ extra_body reasoning_effort, Gemini ต้องไม่ได้ (extra_body=None)
    กัน endpoint OpenAI-compatible ของ Gemini ตอบ 400 จน fallback พัง
    """
    groq_mock, gemini_mock = MagicMock(), MagicMock()
    groq_mock.chat.completions.create.side_effect = _timeout_error()
    gemini_mock.chat.completions.create.return_value = _mock_response("Gemini answer")
    mock_client_factory.side_effect = _two_clients(groq_mock, gemini_mock)

    call_general_ai(
        messages=[{"role": "user", "content": "x"}],
        max_tokens=100,
        request_id="req-effort-gemini",
        reasoning_effort="low",
    )

    groq_kwargs = groq_mock.chat.completions.create.call_args.kwargs
    gemini_kwargs = gemini_mock.chat.completions.create.call_args.kwargs
    assert groq_kwargs["extra_body"] == {"reasoning_effort": "low"}
    assert gemini_kwargs["extra_body"] is None


@patch("app.llm_client._client")
def test_non_reasoning_groq_model_gets_no_effort_and_no_wasted_retry(mock_client_factory):
    """
    [รีวิว PR #21] ถ้า GROQ_MODEL ไม่ใช่ gpt-oss: ไม่ส่ง reasoning_effort และเจอ length แล้วต้อง
    ไม่ retry Groq ซ้ำ (request เดิมเป๊ะ) — ไป Gemini ทันที
    """
    groq_mock, gemini_mock = MagicMock(), MagicMock()
    groq_mock.chat.completions.create.return_value = _mock_response("", finish_reason="length")
    gemini_mock.chat.completions.create.return_value = _mock_response("Gemini answer")
    mock_client_factory.side_effect = _two_clients(groq_mock, gemini_mock)

    with patch.object(config.settings, "GROQ_MODEL", "llama-3.3-70b-versatile"):
        content, _, _ = call_general_ai(
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            request_id="req-non-reasoning",
            reasoning_effort="low",
        )

    assert content == "Gemini answer"
    assert groq_mock.chat.completions.create.call_count == 1
    assert groq_mock.chat.completions.create.call_args.kwargs["extra_body"] is None


@patch("app.llm_client._client")
def test_total_deadline_exhausted_skips_gemini(mock_client_factory):
    """
    [รีวิว PR #21] ถ้า Groq กินเวลาเกือบหมดงบรวม (20s) จนเหลือ < 1s ต้องไม่เรียก Gemini ต่อ
    แต่ raise LLMUnavailableError ทันที (ไม่ให้ router timeout ที่ 25s ไปก่อน)
    ใช้นาฬิกาปลอมแทนการ sleep จริง
    """
    clock = [1000.0]
    groq_mock, gemini_mock = MagicMock(), MagicMock()

    def _slow_groq_timeout(**kwargs):
        clock[0] += 19.5  # งบรวม = 25 - 5 = 20s เหลือ 0.5s
        raise _timeout_error()

    groq_mock.chat.completions.create.side_effect = _slow_groq_timeout
    mock_client_factory.side_effect = _two_clients(groq_mock, gemini_mock)

    with patch("app.llm_client.time.monotonic", side_effect=lambda: clock[0]):
        with pytest.raises(LLMUnavailableError):
            call_general_ai(
                messages=[{"role": "user", "content": "x"}],
                max_tokens=100,
                request_id="req-deadline",
            )

    assert gemini_mock.chat.completions.create.call_count == 0


@patch("app.llm_client._client")
def test_hop_timeout_is_capped_by_remaining_budget(mock_client_factory):
    """
    [รีวิว PR #21] Groq ช้าจนเหลือเวลา 3s ต้องให้ Gemini timeout ไม่เกิน 3s (ไม่ใช่ 6s เต็ม)
    """
    clock = [1000.0]
    groq_mock, gemini_mock = MagicMock(), MagicMock()

    def _slow_groq_timeout(**kwargs):
        clock[0] += 17.0  # เหลือ 3s
        raise _timeout_error()

    groq_mock.chat.completions.create.side_effect = _slow_groq_timeout
    gemini_mock.chat.completions.create.return_value = _mock_response("Gemini answer")
    mock_client_factory.side_effect = _two_clients(groq_mock, gemini_mock)

    with patch("app.llm_client.time.monotonic", side_effect=lambda: clock[0]):
        content, _, _ = call_general_ai(
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            request_id="req-cap",
        )

    assert content == "Gemini answer"
    assert gemini_mock.chat.completions.create.call_args.kwargs["timeout"].read == pytest.approx(3.0)

@patch("app.llm_client._client")
def test_every_hop_uses_the_configured_temperature(mock_client_factory):
    """A low temperature keeps /general from adding made-up details (live A/B on Thai questions)."""
    groq_mock, gemini_mock = MagicMock(), MagicMock()
    groq_mock.chat.completions.create.side_effect = _timeout_error()
    gemini_mock.chat.completions.create.return_value = _mock_response("Gemini answer")
    mock_client_factory.side_effect = _two_clients(groq_mock, gemini_mock)

    call_general_ai(messages=[{"role": "user", "content": "x"}], max_tokens=100, request_id="req-temp")

    assert config.settings.GENERAL_TEMPERATURE == pytest.approx(0.3)
    for mock in (groq_mock, gemini_mock):
        assert mock.chat.completions.create.call_args.kwargs["temperature"] == pytest.approx(0.3)
