"""ปิดบัง PII เบา ๆ (email/เบอร์โทร) — Could feature, ค่าตั้งต้นปิด (PII_MASKING=false)"""

from __future__ import annotations

import re

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"\b0\d{1,2}[- ]?\d{3}[- ]?\d{3,4}\b")


def mask_pii(text: str) -> str:
    text = EMAIL_PATTERN.sub("***", text)
    text = PHONE_PATTERN.sub("***", text)
    return text
