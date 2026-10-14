"""
Config สำหรับ service `engines` (04_ai_engines)
ค่าทั้งหมดตาม CONTRACT.md §8 — ใช้ไลบรารี `openai` ตัวเดียว สลับเจ้าด้วย base_url เท่านั้น
ห้ามลง SDK ของเจ้าอื่นเพิ่ม
"""
import os


class Settings:
    SERVICE_NAME = "engines"
    VERSION = os.getenv("GIT_SHA", "0.1.0")

    # Groq — หลัก
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # Gemini — สำรอง
    GEMINI_BASE_URL = os.getenv(
        "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # งบเวลา: router → engines เพดาน 25s ต่อ hop (CONTRACT.md §0)
    #
    # [รีวิว PR #21 ข้อ 1] worst case ของ call_general_ai คือ 3 hop เรียงกัน:
    #   Groq primary -> Groq retry (low effort, เจอ finish_reason="length") -> Gemini fallback
    # ค่าเดิม 12 + 12 + 10 = 34s เกิน timeout 25s ที่ Router (services/03_ai_router_agent
    # /app/clients.py:59) ตั้งไว้ตอนเรียก /general ทำให้ request อาจถูกตัดก่อน Gemini ตอบกลับมา
    #
    # ปรับให้ worst case ต่ำกว่า ROUTER_TIMEOUT_SECONDS ลบด้วย TIMEOUT_SAFETY_MARGIN_SECONDS
    # (เผื่อ network/serialization overhead ระหว่าง router <-> engines) และ assert ไว้ตอน import
    # กัน env ในอนาคตตั้งค่าจนเกินงบโดยไม่มีใครสังเกต — ดูเทสยืนยันที่
    # tests/test_llm_fallback_timeout.py
    ROUTER_TIMEOUT_SECONDS = float(os.getenv("ROUTER_TIMEOUT_SECONDS", "25"))
    TIMEOUT_SAFETY_MARGIN_SECONDS = float(os.getenv("TIMEOUT_SAFETY_MARGIN_SECONDS", "5"))

    PRIMARY_TIMEOUT_SECONDS = float(os.getenv("GENERAL_PRIMARY_TIMEOUT_SECONDS", "7"))
    FALLBACK_TIMEOUT_SECONDS = float(os.getenv("GENERAL_FALLBACK_TIMEOUT_SECONDS", "6"))

    # D4: จำกัด token ของ /general สองทาง
    #  1) response — เพดานคำตอบที่ให้ LLM สร้าง (ลดจาก D2 เพราะ /general ควรตอบสั้นกระชับ)
    GENERAL_MAX_TOKENS = int(os.getenv("GENERAL_MAX_TOKENS", "350"))
    #  2) input — งบ token โดยประมาณของ (system + history + query) ก่อนยิง LLM
    #     ตัด history เก่าสุดออกก่อนถ้าเกินงบ กัน context โตไม่จำกัดตามความยาวบทสนทนา
    GENERAL_MAX_INPUT_TOKENS = int(os.getenv("GENERAL_MAX_INPUT_TOKENS", "1200"))
    #  3) temperature — ค่าเริ่มต้นของ provider (ราว 1) ทำให้ LLM แต่งรายละเอียดที่ไม่ได้ถามเพิ่ม
    #     0.3 ลดเรื่องแต่งลงชัดเจนเมื่อลองกับคำถามไทยจริง และยังตอบเป็นกันเองอยู่
    GENERAL_TEMPERATURE = float(os.getenv("GENERAL_TEMPERATURE", "0.3"))


settings = Settings()

# [รีวิว PR #21 ข้อ 1] worst case: Groq primary + Groq retry (low effort) + Gemini fallback
# ต้องต่ำกว่า deadline ของผู้เรียก (Router) พร้อม margin เผื่อ overhead — ถ้าใครแก้ env จนงบเวลา
# เกิน จะ import service ไม่ขึ้นทันที (fail fast) แทนที่จะไปโดนตัดคำขอกลางทางตอน production จริง
_worst_case_fallback_seconds = 2 * settings.PRIMARY_TIMEOUT_SECONDS + settings.FALLBACK_TIMEOUT_SECONDS
_deadline_with_margin = settings.ROUTER_TIMEOUT_SECONDS - settings.TIMEOUT_SAFETY_MARGIN_SECONDS
assert _worst_case_fallback_seconds <= _deadline_with_margin, (
    f"งบเวลา fallback รวม (primary*2 + fallback = {_worst_case_fallback_seconds}s) "
    f"เกิน deadline ของ router หลังหัก margin ({_deadline_with_margin}s) — "
    "ปรับ GENERAL_PRIMARY_TIMEOUT_SECONDS/GENERAL_FALLBACK_TIMEOUT_SECONDS "
    "หรือ TIMEOUT_SAFETY_MARGIN_SECONDS ให้งบรวมต่ำกว่านี้"
)