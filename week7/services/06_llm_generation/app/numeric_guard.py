"""Numeric guard — กันเดาตัวเลข (จุดขายของ service) หัวข้อ 8

pure function ไม่ใช้ LLM/เน็ต ทดสอบง่าย ใช้ทั้ง grounded, translate, รายงานประจำสัปดาห์
"""

from __future__ import annotations

import re

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# สกอร์: 1-2 หลัก คั่นด้วย - หรือ : ห้ามชนกับรูปเวลา HH:MM (เวลาจะมี 2 หลักทั้งสองข้างเสมอและมักมี : )
#
# เพิ่ม 2 เงื่อนไขกัน false positive ที่เจอจริง:
#   - (?<!\d{4}-) กันวันที่ ISO เช่น "2026-05-03" ไม่ให้ "05-03" ถูกอ่านเป็นสกอร์
#     (เช็คว่า 4 ตัวอักษรก่อนหน้าไม่ใช่ "XXXX-" ของปี)
#   - negative lookahead ท้าย กันวลีที่ไม่ใช่สกอร์บอลแต่มีรูปแบบตัวเลข-ตัวเลข
#     เช่น "5-10 games", "3-4 นัด" ที่ตามด้วยหน่วยนับ ไม่ใช่ชื่อทีม
#
# หมายเหตุ: นี่คือ heuristic ไม่ใช่การแก้ปัญหาแบบสมบูรณ์ — กรณีคลุมเครืออื่น ๆ
# (เช่น "5-12" ที่บังเอิญเดือนตรง หรือหน่วยนับที่ไม่อยู่ในลิสต์) อาจยังหลุดได้
_NON_SCORE_UNITS = (
    r"games?|matches?|wins?|points?|assists?|days?|minutes?|"
    r"เกม|นัด|แต้ม|วัน|นาที"
)
_SCORE_RE = re.compile(
    r"(?<!\d)(?<!\d{4}-)(\d{1,2})\s*[-:]\s*(\d{1,2})(?!\d)(?!-\d{1,2}\b)"
    rf"(?!\s*(?:{_NON_SCORE_UNITS})\b)"
)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")
_SEASON_RE = re.compile(r"\b(19|20)\d{2}\s*/\s*\d{2}\b")
_CITATION_RE = re.compile(r"\[\d+\](?!\()")
_LIST_MARKER_RE = re.compile(r"(^|\n)\s*\d+[.)]\s")


def normalize_text(text: str) -> str:
    """แปลงเลขไทย→อารบิก, เครื่องหมายขีดต่าง ๆ →'-', ตัด comma พันหลัก"""
    text = text.translate(_THAI_DIGITS)
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    return text


def _strip_non_checkable(text: str) -> str:
    """ตัด citation [n] และเลขลำดับ list ออกก่อนตรวจ เพื่อลด false positive"""
    text = _CITATION_RE.sub("", text)
    text = _LIST_MARKER_RE.sub(lambda m: m.group(1), text)
    return text


def _is_time_like(span_text: str) -> bool:
    return bool(_TIME_RE.fullmatch(span_text.strip()))


def find_score_claims(text: str) -> list[tuple[int, int]]:
    """หาคู่ตัวเลขที่ดูเหมือนสกอร์ในคำตอบ (a, b) — กันเวลา/ปี/matchweek"""
    normed = normalize_text(_strip_non_checkable(text))
    claims: list[tuple[int, int]] = []
    for match in _SCORE_RE.finditer(normed):
        whole = match.group(0)
        if _is_time_like(whole):
            continue
        # ปี 2026/27 ไม่ใช่ score pattern ("-") อยู่แล้วเพราะใช้ "/" ข้าม
        a, b = int(match.group(1)), int(match.group(2))
        # สกอร์บอลปกติไม่เกิน ~20 ต่อฝั่ง (กันเลขอันดับ/แต้มติดกันบังเอิญ เช่น "1-0" ผ่าน, "2026-27" ถูกกรองเพราะมี /)
        if a <= 20 and b <= 20:
            claims.append((a, b))
    return claims


def score_in_source(pair: tuple[int, int], known_scores: set[tuple[int, int]]) -> bool:
    a, b = pair
    return (a, b) in known_scores or (b, a) in known_scores


def check_score_mismatch(
    text: str, known_scores: set[tuple[int, int]]
) -> list[tuple[int, int]]:
    """คืนรายการคู่สกอร์ที่อ้างในคำตอบแต่ไม่พบใน known_scores (hard violation)"""
    claims = find_score_claims(text)
    return [c for c in claims if not score_in_source(c, known_scores)]


def extract_standalone_numbers(text: str) -> list[str]:
    """ตัวเลขอื่น ๆ ที่ไม่ใช่สกอร์/เวลา/ปี/matchweek สำหรับ soft check"""
    normed = normalize_text(_strip_non_checkable(text))
    normed = _TIME_RE.sub(" ", normed)
    normed = _SEASON_RE.sub(" ", normed)
    normed = _SCORE_RE.sub(" ", normed)
    return re.findall(r"\d+", normed)


def numbers_not_in_context(text: str, context_text: str) -> list[str]:
    """soft check: ตัวเลขในคำตอบที่ไม่ปรากฏในข้อความ context เลย"""
    context_normed = normalize_text(context_text)
    answer_nums = extract_standalone_numbers(text)
    missing = [n for n in answer_nums if n not in context_normed]
    return missing
