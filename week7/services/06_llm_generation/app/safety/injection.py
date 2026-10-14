"""ตรวจ pattern prompt injection ในเนื้อ context — บล็อกก่อนเรียก LLM (เหมือน gambling.py)
เดิม detect_injection() แค่ log ไม่เคยใช้บล็อกจริง ทำให้ผลไม่คงเส้นคงวา:
คำตอบสุดท้ายขึ้นอยู่กับว่า LLM ตัวไหนจะ "เผลอทำตาม" คำสั่งแปลกปลอมหรือเปล่า
(mock บล็อกได้เพราะบังเอิญตอบซ้ำคำที่ทำให้ canary leak ตรวจเจอ, provider จริงไม่ทำตาม
คำสั่งแปลกปลอมเลยไม่มี canary leak ให้ตรวจเจอ -> blocked=False ทั้งที่ input มี pattern ชัดเจน)
แก้ให้ตรวจจาก context/input โดยตรงและบล็อกทันที ไม่ต้องรอดูว่า LLM จะหลุดหรือไม่
"""

from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"ignore the above",
    r"disregard (all )?(previous|prior) instructions",
    r"ลืมคำสั่งก่อนหน้า",
    r"เพิกเฉยคำสั่งก่อนหน้า",
    r"system prompt",
    r"you are now (an?|the) (ai|assistant|chatbot|bot|language model|llm)",
    # เดิม r"act as" กว้างเกินไป จับ "act as captain" (บริบทกีฬาปกติ) ผิด
    # แก้ให้เจาะจงเฉพาะกรณี "act as" ตามด้วยคำที่บ่งชี้ persona/AI/jailbreak จริง ๆ
    # ครอบด้วยวงเล็บให้ implicit string concat ชัดเจน (กัน ISC004) และแต่ละบรรทัด
    # ไม่เกิน 88 ตัวอักษรตาม ruff format — เดิมเยื้อง 1 space ทำให้ format ไม่ผ่าน
    (
        r"act as (an?|the) (ai|assistant|chatbot|bot|language model|llm|gpt|dan|"
        r"jailbreak|unrestricted|developer mode)"
    ),
    r"new instructions?:",
]


def detect_injection(text: str) -> bool:
    """เช็ค pattern ของ prompt injection ใน context/input"""
    for pat in INJECTION_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            return True
    return False


def detect_prompt_leak(answer: str, canary: str) -> bool:
    """คำตอบมี canary token ของ system prompt หรือไม่ (สัญญาณเสริม หลังเรียก LLM แล้ว)"""
    return bool(canary and canary in answer)


def should_block_injection(context_text: str) -> bool:
    """ใช้ตัวนี้เป็นจุดตัดสินใจหลักก่อนเรียก LLM — เหมือนแนวทางของ gambling.py
    บล็อกทันทีถ้าเจอ pattern ใน context โดยไม่ต้องรอดูคำตอบของ LLM ก่อน
    ทำให้ผลลัพธ์คงเส้นคงวาไม่ว่าจะใช้ mock หรือ provider จริงตัวไหน
    """
    return detect_injection(context_text)
