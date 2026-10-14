"""
D5 — วิธีที่ 3: ถาม LLM ตรง ๆ ให้จำแนก intent (few-shot prompt ผ่าน Groq/Gemini เดิม)

ใช้ app.llm_client.call_general_ai ตัวเดียวกับ /general (ได้ fallback Groq→Gemini ฟรี)
แค่เปลี่ยน system prompt ให้ตอบ JSON เดียว: {"intent": "..."}

[ข้อ 3 — แก้ตาม review] เดิมตั้ง max_tokens=50 กับ gpt-oss-120b (โมเดล reasoning บน Groq)
token ที่ใช้ "คิด" ก่อนตอบมักหมดก่อนได้คำตอบจริง ทำให้ Groq ตอบ finish_reason="length"
แล้ว call_general_ai fallback ไป Gemini แทบทุกครั้ง แถว "LLM (Groq/Gemini)" ในผลเปรียบเทียบ
จึงอาจเป็นผลของ Gemini อย่างเดียว ไม่ใช่ few-shot ผ่าน Groq จริง ๆ แก้ 2 ทาง:
  1. เพิ่ม max_tokens (50 -> 300) ให้มีที่เหลือพอหลังหักโควตา reasoning
  2. ส่ง reasoning_effort="low" ผ่าน call_general_ai (ลดโควตา reasoning ตั้งแต่ต้น แทนที่จะเผื่อ
     max_tokens เยอะ ๆ เฉย ๆ) งานนี้แค่ต้องการ label เดียว ไม่ต้อง reasoning ลึกอยู่แล้ว
  3. classify_one คืน model ที่ตอบจริงกลับมาด้วย (ไม่ใช่ทิ้งด้วย _model เหมือนเดิม) เพื่อให้
     train_and_eval สรุปสัดส่วน Groq vs Gemini ท้ายผลได้ — เป็นคำตอบให้ข้อเสนอที่สองของ reviewer
     ("log ว่าแต่ละคำตอบมาจาก provider ไหน") ด้วย
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm_client import call_general_ai  # noqa: E402

CLASSIFY_MAX_TOKENS = 300  # เดิม 50 — ดู docstring ข้อ 3 ด้านบน

INTENTS = [
    "trivia_history",
    "match_result",
    "fixture_schedule",
    "standings_stats",
    "weekly_summary",
    "general_football",
    "prediction",
    "out_of_scope",
]

SYSTEM_PROMPT = (
    "คุณเป็นตัวจำแนกประเภทคำถาม (intent classifier) สำหรับผู้ช่วยฟุตบอล Premier League\n"
    f"จำแนกคำถามให้อยู่ใน 1 ใน 8 หมวดนี้เท่านั้น: {', '.join(INTENTS)}\n"
    'ตอบเป็น JSON บรรทัดเดียวเท่านั้น รูปแบบ: {"intent": "<หนึ่งใน 8 ค่าข้างบน>"} '
    "ห้ามมีข้อความอื่นนอกจาก JSON นี้"
)


def classify_one(text: str, request_id: str) -> tuple[str, str]:
    """คืน (label, model_used) — model_used เอาไว้สรุปว่าคำตอบมาจาก Groq หรือ Gemini จริง ๆ"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    content, model_used, _usage = call_general_ai(
        messages=messages,
        max_tokens=CLASSIFY_MAX_TOKENS,
        request_id=request_id,
        # แค่ต้องการ label เดียว ไม่ต้องคิดลึก — ดู docstring ข้อ 3
        # (llm_client ส่งต่อเฉพาะ Groq gpt-oss; ตอน fallback ไป Gemini จะไม่ส่ง field นี้)
        reasoning_effort="low",
    )
    match = re.search(r'"intent"\s*:\s*"(\w+)"', content)
    label = match.group(1) if match else content.strip()
    label = label if label in INTENTS else "out_of_scope"  # กันโมเดลตอบนอกรายการ
    return label, model_used


def train_and_eval(X_test, y_test) -> float:
    """LLM แบบ few-shot ไม่ต้อง "เทรน" — เรียกตรงต่อประโยคแล้ววัด accuracy บน test set เลย"""
    correct = 0
    model_counts: Counter[str] = Counter()
    for i, (text, true_label) in enumerate(zip(X_test, y_test)):
        pred, model_used = classify_one(text, request_id=f"eval-llm-{i}")
        model_counts[model_used] += 1
        if pred == true_label:
            correct += 1

    # [ข้อ 3] สรุปให้เห็นชัดว่าคำตอบมาจากโมเดล/provider ไหนบ้างกี่ครั้ง — ถ้าเป็น Gemini เกือบ
    # 100% แปลว่า Groq ยัง fallback บ่อยอยู่ (max_tokens/reasoning_effort ยังไม่พอ) ต้องดูต่อ
    print(f"[llm_classifier] คำตอบแยกตามโมเดลที่ตอบจริง ({len(y_test)} เคส): {dict(model_counts)}")

    return correct / len(y_test)