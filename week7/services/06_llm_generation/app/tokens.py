"""ตัวประมาณจำนวน token แบบไม่ใช้ tiktoken (ตามหัวข้อ 5 — ห้ามใช้ tiktoken)

ค่าจริงอ่านจาก usage ที่ provider ส่งกลับมาเสมอ ตัวนี้ใช้แค่ประมาณเพื่อคุมงบ context ก่อนยิง LLM
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """ประมาณคร่าว ๆ: อังกฤษ ~4 ตัวอักษร/token, ไทยหนาแน่นกว่า ~2 ตัวอักษร/token"""
    if not text:
        return 0
    thai_chars = sum(1 for c in text if "\u0e00" <= c <= "\u0e7f")
    other_chars = len(text) - thai_chars
    return int(thai_chars / 2 + other_chars / 4) + 1
