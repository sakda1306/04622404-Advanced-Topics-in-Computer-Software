"""Layer 2, no LLM: Thai and English keywords per route (Design.md §4.6).

A message that hits two routes goes to the LLM layer, because FR-11 allows only one route.
"""

from __future__ import annotations

import re

from app.router.decision import Decision

RULE_CONFIDENCE = 0.9


def _en(words: str) -> str:
    # Word limits by hand: \b finds none between Thai and Latin letters written without a space.
    return rf"(?<![a-z0-9])(?:{words})(?![a-z0-9])"


_ROUTE_PATTERNS = {
    "skill_assessment": re.compile(rf"(?<!เพิ่ม)ทักษะ|สกิล|จุดแข็ง|{_en(r'skills?|strengths?')}"),
    "work_style": re.compile(
        rf"รูปแบบการทำงาน|สไตล์การทำงาน|ชอบทำงาน|{_en(r'work\s*style')}",
    ),
    "blind_spots": re.compile(rf"จุดอ่อน|จุดบอด|{_en(r'blind\s*spots?|weakness(?:es)?')}"),
    "job_matching": re.compile(
        r"^สายงาน$|สายงานไหน|(?<!เคยทำ)งานไหน(?!.*(?:นาน|ล่าสุด|แรก|ก่อนหน้า|ที่ผ่านมา|เคย))"  # past jobs
        r"|ควร(?:เริ่ม)?(?:เรียน|เก็บ|ฝึก|เพิ่ม)"
        rf"|{_en(r'match(?:es)?|which\s+(?:role|job)|next\s+steps?')}",
    ),
    "salary": re.compile(
        r"เงินเดือน|ค่าตอบแทน|ค่าจ้าง"
        rf"|{_en(r'salary|salaries|pay\s+(?:range|rate|scale)|(?:average|typical|the)\s+pay')}"
    ),
    "market": re.compile(rf"ตลาดงาน|ตำแหน่งงาน|เปิดรับ|{_en(r'job\s+market|demand|openings?')}"),
    "experience": re.compile(rf"ประสบการณ์|{_en(r'experience')}"),
}

_EDIT = re.compile(
    r"^(?:ช่วย|ขอ|กรุณา)?\s*(?:"
    r"(?:เปลี่ยน|แก้ไข|แก้|ปรับ|เพิ่ม)\s*"
    r"(?:ทักษะ|ระดับ|สายงาน|พื้นที่|รูปแบบการทำงาน|เงินเดือน|จังหวัด|โปรไฟล์|ประสบการณ์)"
    r"|ลบ\s*\S|เอา\s*\S.*ออก(?!มา)"
    r")"
    r"|แก้(?:ให้|เป็น)|อัป?เดตให้|อัพเดตให้"
    r"|^(?:please\s+)?(?:remove|delete)\s+.+\s+from\s+(?:(?:the|my)\s+)?(?:skills?|profile)"
    r"|^(?:please\s+)?add\s+.+\s+to\s+(?:(?:the|my)\s+)?(?:skills?|profile)"
    r"|^(?:please\s+)?(?:add|remove|delete|change|update|edit)\s+"
    r"(?:(?:the|my)\s+)?(?:skill|level|role|salary|profile)"
    r"|^(?:please\s+)?(?:change|update|edit|set)\s+(?:(?:the|my)\s+)?\S+\s+experience"
)
_QUESTION = re.compile(
    r"อะไร|ไหน|ไหม|มั้ย|ยังไง|อย่างไร|ทำไง|ทำไม|หรือเปล่า|รึเปล่า|เท่าไหร่|เท่าไร|กี่|ควร|\?"
    rf"|^{_en(r'what|how|which|who|why|when|where|should|can|could|do|does|is|are|will|would')}"
)


# "ไม่ได้ใช้อะไรแล้ว" holds a question word but asks nothing.
_NOT_ASKING = re.compile(r"ไม่(?:ได้|มี)\S*\s*อะไร")
# Said with a route's keyword, these ask to change the profile wherever they are in the sentence.
_SAYS_CHANGE = re.compile(
    r"เปลี่ยนเป็น|ขอเป็น|ต้องเป็น|ตั้งเป็น|ตั้งระดับ|เอาออก|ออกให้|แก้โปรไฟล์|ผิด"
    r"|ที่(?:อยากได้|ต้องการ|คาดหวัง|รับได้).*\d{4}|(?:อยากได้|ต้องการ)\s*เงินเดือน.*\d{4}"
)
# A keyword names the topic, but these ask something else about it: the LLM reads the whole message.
_NOT_THE_KEYWORD = re.compile(r"ไม่ได้ถาม|@")
_ASKS_ABOUT_A_JOB = re.compile(
    rf"ต้อง(?:ใช้|มี|การ|รู้|เก็บ|เรียน|ฝึก|เพิ่ม)|สมัคร|{_en(r'requires?|needs?')}"
)
# An order about how to answer from now on, whichever route's keyword it names.
_ORDERS_THE_ANSWERS = re.compile(
    r"(?:จากนี้ไป|ต่อจากนี้|ต่อไปนี้|นับจากนี้)\s*(?:ให้|ต้อง)\s*ตอบ|ตอบ\s*route|route\s*(?:ต้อง)?เป็น"
    rf"|{_en(r'from\s+now\s+on')}"
)
_ABOUT_THE_USER = frozenset({"skill_assessment", "experience"})
_TELLING_A_PREFERENCE = "ชอบทำงาน"


def is_question(message: str) -> bool:
    """Expects the text from `normalize`."""
    return _QUESTION.search(_NOT_ASKING.sub("", message)) is not None


def _needs_the_whole_message(route: str, message: str, asks: bool) -> bool:
    if _NOT_THE_KEYWORD.search(message):
        return True
    if route in _ABOUT_THE_USER and _ASKS_ABOUT_A_JOB.search(message):
        return True
    return route == "work_style" and _TELLING_A_PREFERENCE in message and not asks


def match_rules(message: str) -> Decision | None:
    """Expects the text from `normalize`, which `decide` passes in."""
    if _ORDERS_THE_ANSWERS.search(message):
        return None
    asks = is_question(message)
    if _EDIT.search(message) and not asks:
        return Decision(route="profile_edit", confidence=RULE_CONFIDENCE, layer="rules")
    hits = [route for route, pattern in _ROUTE_PATTERNS.items() if pattern.search(message)]
    if hits and not asks and _SAYS_CHANGE.search(message):
        return Decision(route="profile_edit", confidence=RULE_CONFIDENCE, layer="rules")
    if len(hits) == 1 and not _needs_the_whole_message(hits[0], message, asks):
        return Decision(route=hits[0], confidence=RULE_CONFIDENCE, layer="rules")
    return None
