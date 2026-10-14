"""ตรวจคำขอ/คำตอบเกี่ยวกับการพนัน (ห้ามให้ทีเด็ด/อัตราต่อรอง/ชวนเล่นพนัน)"""

from __future__ import annotations

import re
import unicodedata

from app.safety.lexicon import (
    GAMBLING_ODDS_PATTERN,
    GAMBLING_PROMOTION_PATTERNS,
    GAMBLING_REQUEST_PATTERNS,
    GAMBLING_TIPS_PATTERNS,
)

REFUSAL_TH = (
    "ขออภัย ระบบนี้ไม่ให้ทีเด็ด อัตราต่อรอง หรือคำแนะนำการเดิมพัน "
    "หากสนใจผลการแข่งขัน ตารางคะแนน หรือสถิติ ถามได้เลย"
)
REFUSAL_EN = (
    "Sorry, I can't provide betting tips, odds or gambling advice. "
    "I'm happy to help with match results, standings or stats."
)


def _normalize(text: str) -> str:
    """normalize ช่องว่าง/ตัวพิมพ์เล็ก/ตัวอักษรซ้ำ เพื่อจับการเลี่ยงคำ"""
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"\s+", " ", t)
    # ตัดตัวอักษรซ้ำติดกัน >=3 ตัวให้เหลือ 1 (เช่น "ทีเดดดด" เลี่ยงคำ)
    t = re.sub(r"(.)\1{2,}", r"\1", t)
    return t


def _nospace(text: str) -> str:
    """ตัดช่องว่างทั้งหมดออก เพื่อจับการเลี่ยงคำแบบเว้นวรรคเป็นตัว ๆ (เช่น 'ที เด็ด')"""
    return re.sub(r"\s+", "", text)


def _any_match(patterns: list[str], text: str) -> bool:
    normed = _normalize(text)
    nospace = _nospace(normed)
    for pat in patterns:
        if re.search(pat, normed, flags=re.IGNORECASE):
            return True
        # ลองกับ pattern ที่ตัดช่องว่างออกด้วย เทียบกับข้อความที่ตัดช่องว่างแล้ว
        if re.search(re.sub(r"\s+", "", pat), nospace, flags=re.IGNORECASE):
            return True
    return False


def check_query(query: str) -> str | None:
    """pre-check บน query ก่อนเรียก LLM — คืน reason ถ้าควรบล็อก"""
    if _any_match(GAMBLING_REQUEST_PATTERNS, query):
        return "gambling_request"
    return None


def check_answer(answer: str, *, allow_context_odds: bool = False) -> str | None:
    """post-check บน answer — คืน reason ถ้าควรบล็อก

    allow_context_odds: True สำหรับ grounded ที่ odds มาจาก context จริง (เกร็ดประวัติ)
    ใน passthrough ไม่มี context จึงเข้มกว่าเสมอ (allow_context_odds=False)
    """
    if _any_match(GAMBLING_TIPS_PATTERNS, answer):
        return "gambling_tips"
    if _any_match(GAMBLING_PROMOTION_PATTERNS, answer):
        return "gambling_promotion"
    normed = _normalize(answer)
    if not allow_context_odds and re.search(
        GAMBLING_ODDS_PATTERN, normed, flags=re.IGNORECASE
    ):
        return "gambling_odds"
    return None


def refusal_text(language: str) -> str:
    return REFUSAL_TH if language == "th" else REFUSAL_EN
