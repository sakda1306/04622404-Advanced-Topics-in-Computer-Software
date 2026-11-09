"""Fixed Thai replies for conversation that needs no LLM, and how follow-up questions move on.

Pure Python (Design.md §4.1, §4.6).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

_ABILITIES_TH = (
    "ผมช่วยดูทักษะของคุณ รูปแบบการทำงาน จุดที่ควรระวัง สายงานที่เหมาะและสิ่งที่ควรเรียนต่อ "
    "เงินเดือน ตลาดงาน ประสบการณ์ และแก้โปรไฟล์ให้ได้ถ้าพิมพ์บอก "
    "ลองถามเช่น “สายงานไหนเหมาะกับฉัน” หรือ “เงินเดือน QA เท่าไหร่”"
)
_ABILITIES_BEFORE_PROFILE_TH = (
    "ตอนนี้ผมช่วยเก็บข้อมูลเพื่อสร้างโปรไฟล์ และตอบเรื่องเงินเดือนกับตลาดงานได้เลยครับ "
    "หลังสร้างโปรไฟล์แล้ว ถามเรื่องทักษะ จุดที่ควรระวัง และสายงานที่เหมาะได้"
)
_TELL_HOW_TH = "ถ้าไม่เห็นการ์ด พิมพ์บอกสิ่งที่อยากแก้อีกครั้งได้ครับ"
_REPLIES_TH = {
    "thanks": "ยินดีครับ มีอะไรถามต่อได้เลย",
    "ack": "รับทราบครับ มีอะไรถามต่อได้เลย",
    "feeling": (
        "ช่วงหางานเครียดได้จริงครับ ค่อย ๆ ไปทีละขั้นก็พอ อยากเริ่มจากดูว่าควรเรียนอะไรต่อ หรือดูสายงานที่เหมาะก่อนดีครับ"
    ),
    "account": "ลบบัญชีได้ที่หน้าบัญชีครับ ผมลบให้จากแชทไม่ได้ เพราะลบแล้วข้อมูลทั้งหมดจะหายถาวร",
    "skip": "ไม่เป็นไรครับ",
    "unsure": "ไม่เป็นไรครับ",
}
ASK_WHICH_ROLE_TOPIC_TH = "อยากรู้เรื่องไหนของ {title} ครับ ทักษะที่ต้องใช้ เงินเดือน หรือตลาดงาน"
STUCK_ON_SKILLS_TH = "ถ้ากำลังเรียนอยู่ บอกเป็นระดับ 1 ได้เลยครับ หรือจะไปทำแบบสอบถาม หรืออัปโหลด CV แทนก็ได้"
_FORM_KINDS = frozenset({"skip", "unsure"})
_MAX_TIMES_ASKED = 2


def _confirm_or_refuse(kind: str, *, has_pending_edit: bool) -> str:
    if not has_pending_edit:
        return "ตอนนี้ไม่มีรายการที่รอให้ยืนยันครับ ถ้าอยากแก้โปรไฟล์ พิมพ์บอกได้เลย"
    if kind == "confirm":
        return f"ถ้าข้อมูลถูกต้อง กดปุ่มยืนยันบนการ์ดได้เลยครับ ข้อมูลจะเปลี่ยนหลังกดปุ่มเท่านั้น {_TELL_HOW_TH}"
    return f"กดปุ่มยกเลิกบนการ์ดได้เลยครับ ข้อมูลในโปรไฟล์จะไม่เปลี่ยน {_TELL_HOW_TH}"


def small_talk_reply(kind: str, *, has_profile: bool, has_pending_edit: bool = False) -> str:
    if kind in ("confirm", "refuse"):
        return _confirm_or_refuse(kind, has_pending_edit=has_pending_edit)
    abilities = _ABILITIES_TH if has_profile else _ABILITIES_BEFORE_PROFILE_TH
    if kind == "greeting":
        return f"สวัสดีครับ {abilities}"
    if kind == "ready" and has_profile:
        return "คุณมีโปรไฟล์แล้วครับ ถามต่อหรือพิมพ์บอกสิ่งที่อยากแก้ได้เลย"
    if kind in _FORM_KINDS and has_profile:
        return f"ไม่เป็นไรครับ {abilities}"
    return _REPLIES_TH.get(kind, abilities)


def slots_to_leave(
    messages: Iterable[tuple[str, str]],
    questions: Mapping[str, str],
    *,
    skip_said: Iterable[str],
) -> set[str]:
    """Slots not to ask about again: asked twice already, or the user said to skip or does not know.

    `messages` are (role, text), oldest first. The caller keeps required slots out of the result.
    """
    said = set(skip_said)
    asked: dict[str, int] = {}
    left: set[str] = set()
    current: str | None = None
    for role, text in messages:
        if role == "user":
            if current is not None and text in said:
                left.add(current)
            continue
        current = next((slot for slot, question in questions.items() if question in text), None)
        if current is not None:
            asked[current] = asked.get(current, 0) + 1
            if asked[current] >= _MAX_TIMES_ASKED:
                left.add(current)
    return left
