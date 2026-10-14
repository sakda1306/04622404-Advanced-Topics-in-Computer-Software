"""ตรวจภาษาแบบนับสัดส่วนอักษรไทย (ไม่เรียก LLM) — ใช้ใน passthrough หัวข้อ 7"""

from __future__ import annotations

import re

_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_LETTER_RE = re.compile(r"[^\W\d_]", flags=re.UNICODE)


def thai_ratio(text: str) -> float:
    letters = _LETTER_RE.findall(text)
    if not letters:
        return 0.0
    thai = [c for c in letters if _THAI_RE.match(c)]
    return len(thai) / len(letters)


def language_matches(text: str, language: str) -> bool:
    ratio = thai_ratio(text)
    if language == "th":
        return ratio >= 0.30
    if language == "en":
        return ratio < 0.05
    return True


def language_name(language: str) -> str:
    return "ไทย" if language == "th" else "English"
