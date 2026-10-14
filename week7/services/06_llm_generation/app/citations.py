"""จัดการ citation [n]: normalize, ตัดที่ไม่มีจริง, map sources — ห้าม renumber"""

from __future__ import annotations

import re

# จับเฉพาะ [ตัวเลขล้วน] หรือ [1, 2] / [1,2] — ไม่ยุ่ง markdown link [text](url)
_BRACKET_NUMS_RE = re.compile(r"\[\s*(\d+(?:\s*,\s*\d+)*)\s*\](?!\()")
# 【1】 รูปแบบวงเล็บญี่ปุ่น
_FULLWIDTH_RE = re.compile(r"【\s*(\d+)\s*】")


def normalize_citations(text: str) -> str:
    """แปลง [1, 2] / 【1】 → [1][2]"""

    def _split(match: re.Match) -> str:
        nums = re.findall(r"\d+", match.group(1))
        return "".join(f"[{n}]" for n in nums)

    text = _FULLWIDTH_RE.sub(lambda m: f"[{m.group(1)}]", text)
    text = _BRACKET_NUMS_RE.sub(_split, text)
    return text


def extract_cited_refs(text: str) -> list[int]:
    """คืนรายการเลข ref ที่ถูกอ้างในข้อความ (หลัง normalize แล้ว) เรียงตามที่พบ ไม่ซ้ำ"""
    found = []
    for m in re.finditer(r"\[(\d+)\](?!\()", text):
        n = int(m.group(1))
        if n not in found:
            found.append(n)
    return found


def strip_invalid_citations(text: str, valid_refs: set[int]) -> tuple[str, int]:
    """ตัด [n] ที่ n ไม่มีใน valid_refs ทิ้ง คืน (ข้อความใหม่, จำนวนที่ตัด)"""
    removed = 0

    def _repl(m: re.Match) -> str:
        nonlocal removed
        n = int(m.group(1))
        if n in valid_refs:
            return m.group(0)
        removed += 1
        return ""

    new_text = re.sub(r"\[(\d+)\](?!\()", _repl, text)
    # จัดช่องว่างที่เหลือให้เรียบร้อย (เว้นวรรคซ้ำจากการตัด)
    new_text = re.sub(r"[ \t]{2,}", " ", new_text)
    new_text = re.sub(r"[ \t]+\n", "\n", new_text)
    return new_text, removed


def strip_all_citations(text: str) -> str:
    new_text = re.sub(r"\[(\d+)\](?!\()", "", text)
    new_text = re.sub(r"[ \t]{2,}", " ", new_text)
    return new_text
