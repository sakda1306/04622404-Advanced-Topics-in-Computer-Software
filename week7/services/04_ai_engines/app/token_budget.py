"""
D4 — จำกัด token ของ /general

ไม่ใช้ tiktoken/tokenizer ของจริง เพราะ:
  - Groq/Gemini ใช้ tokenizer คนละตัวกัน ไม่มี tokenizer เดียวที่ตรงทั้งคู่ 100% อยู่แล้ว
  - เป้าหมายคือ "กันหลุด" ไม่ให้ context ยาวจนงบเวลา/ค่าใช้จ่ายบานปลาย ไม่ใช่นับ token เป๊ะเพื่อเรียกเก็บเงิน
  - ตัวประมาณแบบ char-based เร็ว ไม่ต้องโหลดโมเดล/dependency เพิ่ม เพียงพอสำหรับงานนี้

Rule of thumb ที่ใช้: ข้อความผสมไทย/อังกฤษ ~2.2 ตัวอักษรต่อ 1 token (ไทยหนักกว่าอังกฤษต่อ token
เพราะไม่มีช่องว่างคั่นคำ) — ประมาณสูงกว่าความเป็นจริงเล็กน้อยโดยตั้งใจ (กันเกินงบดีกว่าเกินจริง)
"""
from typing import Sequence

CHARS_PER_TOKEN_ESTIMATE = 2.2


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN_ESTIMATE))


def trim_history_to_budget(
    history: Sequence[dict], *, system_prompt: str, query: str, max_input_tokens: int
) -> list[dict]:
    """
    ตัด history เก่าสุดออกทีละข้อความจนกว่า (system + history ที่เหลือ + query) จะอยู่ในงบ
    เก็บข้อความ "ใหม่สุด" ไว้ก่อนเสมอ เพราะ context ที่ใกล้คำถามปัจจุบันมีประโยชน์กว่า
    """
    reserved = estimate_tokens(system_prompt) + estimate_tokens(query)
    budget_for_history = max(0, max_input_tokens - reserved)

    kept: list[dict] = []
    running = 0
    # เดินจากท้าย (ใหม่สุด) ไปหัว (เก่าสุด) แล้วค่อยกลับลำดับตอนจบ
    for msg in reversed(list(history)):
        cost = estimate_tokens(msg.get("content", ""))
        if running + cost > budget_for_history:
            break
        kept.append(msg)
        running += cost

    kept.reverse()
    return kept
