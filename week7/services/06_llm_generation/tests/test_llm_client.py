"""เทส _is_empty_content โดยตรง (pure function ไม่ต้อง mock OpenAI SDK)

ครอบคลุมบั๊กจากรีวิว: finish_reason == "length" ที่มีข้อความบางส่วนติดมาด้วย
ต้องถือว่าใช้ไม่ได้ (ต้อง fallback ไป provider สำรอง) — เดิมเงื่อนไขผิดทำให้
กรณีนี้หลุดผ่านเป็น "สำเร็จ" เสมอ
"""

from __future__ import annotations

from app.llm.client import _is_empty_content


def test_empty_text_is_empty():
    assert _is_empty_content("", None) is True
    assert _is_empty_content(None, None) is True
    assert _is_empty_content("   ", "stop") is True


def test_normal_completion_not_empty():
    assert _is_empty_content("สวัสดีครับ", "stop") is False


def test_length_finish_with_partial_text_is_treated_as_invalid():
    """เคสที่รีวิวเจอบั๊ก: มีข้อความบางส่วน แต่ถูกตัดกลางคันเพราะ token limit
    ต้องถือว่าใช้ไม่ได้ (True) เพื่อให้ chat() ลอง fallback provider สำรอง
    """
    assert _is_empty_content("partial answer that got cut", "length") is True


def test_length_finish_with_empty_text_is_empty():
    assert _is_empty_content("", "length") is True


def test_stop_finish_with_full_text_is_not_empty():
    assert _is_empty_content("คำตอบเต็มปกติ จบด้วย stop", "stop") is False
