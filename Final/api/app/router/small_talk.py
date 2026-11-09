"""Messages that are conversation, not a question for a route (Design.md §4.6).

These need no LLM. A kind from `_WHOLE` must be the whole message, so "ไม่รู้ SQL เลย" stays an answer.
"""

from __future__ import annotations

import re

_ENDING = re.compile(r"(?:ครับผม|ครับ|ค่ะ|คะ|นะ|จ้า|จ้ะ|ฮะ|[\s!.?,ๆ])+$")
_WHOLE = {
    "greeting": re.compile(r"สวัสดี|หวัดดี|hello|hi|hey"),
    "thanks": re.compile(r"ขอบคุณ(?:มาก)?|ขอบใจ(?:มาก)?|thanks?(?: you)?|thx"),
    "ack": re.compile(r"โอเค|ok|okay|เข้าใจแล้ว|รับทราบ|ได้เลย|อ๋อ|อืม+|55+|ฮ่า+"),
    "confirm": re.compile(r"ยืนยัน|ตกลง|ใช่|ใช่แล้ว|ถูกต้อง|confirm|yes"),
    "refuse": re.compile(r"ไม่เอา(?:แล้ว)?|ยกเลิก|ไม่ยืนยัน|ไม่ใช่|cancel|no"),
    "skip": re.compile(r"(?:ขอ)?ข้าม(?:ได้ไหม|ได้มั้ย|ก่อน|ไปก่อน)?|skip"),
    "unsure": re.compile(r"(?:ยัง)?ไม่รู้(?:จะตอบยังไง)?|ไม่ทราบ|ไม่แน่ใจ|ตอบไม่ได้|นึกไม่ออก|idk"),
}
_ANYWHERE = {
    "account": re.compile(r"ลบบัญชี|delete (?:my )?account"),
    "capabilities": re.compile(
        r"ทำอะไรได้บ้าง|ช่วยอะไรได้บ้าง|ทำอะไรต่อ|เริ่มยังไง|เริ่มตรงไหน|ใช้งานยังไง|what can you do"
    ),
    "ready": re.compile(r"สร้างโปรไฟล์ได้|พร้อมสร้างโปรไฟล์"),
    "feeling": re.compile(r"เครียด|ท้อ(?!ง)|กังวล|หมดกำลังใจ"),
}


def small_talk_kind(text: str) -> str | None:
    """Expects the text from `normalize`."""
    plain = _ENDING.sub("", text)
    for kind, pattern in _WHOLE.items():
        if pattern.fullmatch(plain):
            return kind
    for kind, pattern in _ANYWHERE.items():
        if pattern.search(text):
            return kind
    return None
