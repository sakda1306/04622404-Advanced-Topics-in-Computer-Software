"""LLM ปลอม deterministic สำหรับ dev/CI/เดโม — ไม่ต้องมี key ไม่ต่อเน็ต

พยายามตอบให้สมจริงพอควรจากเนื้อหา <references> / <draft> / <data> ที่ส่งเข้ามา
เพื่อให้ทดสอบ citation / numeric guard / safety ได้ครบ
"""

from __future__ import annotations

import json
import re

from app.llm.client import LLMResult, TokenUsage


class MockLLMClient:
    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        deadline: float,
        purpose: str,
    ) -> LLMResult:
        user_content = ""
        for m in messages:
            if m["role"] == "user":
                user_content = m["content"]
        text = self._respond(user_content, purpose)
        return LLMResult(
            text=text,
            model="mock/llm",
            provider="mock",
            usage=TokenUsage(input=len(user_content) // 4, output=len(text) // 4),
            fallback_used=False,
            latency_ms=5,
        )

    def _respond(self, user_content: str, purpose: str) -> str:
        if purpose == "report_highlights":
            return self._respond_report(user_content)
        if purpose == "translate":
            return self._respond_translate(user_content)
        return self._respond_grounded(user_content)

    def _respond_grounded(self, user_content: str) -> str:
        refs = re.findall(
            r'<ref n="(\d+)"[^>]*>\s*title:\s*(.*?)\n\s*text:\s*(.*?)\n?\s*</ref>',
            user_content,
            flags=re.DOTALL,
        )
        if not refs:
            return "ไม่พบข้อมูลที่เพียงพอในคลังข้อมูลเพื่อตอบคำถามนี้"
        # ใช้ context แรกที่เกี่ยวข้องที่สุดเป็นคำตอบ mock แบบง่าย ๆ
        n, title, body = refs[0]
        snippet = body.strip().split("\n")[0][:200]
        return f"{title.strip()} — {snippet} [{n}]"

    def _respond_translate(self, user_content: str) -> str:
        # ระวัง: system/user prompt เอง มีคำว่า "<draft>" โผล่ในประโยคคำสั่งด้วย
        # ("แปลข้อความใน <draft> เป็นภาษา...") ถ้าใช้ <draft>\s*(.*?)\s*</draft>
        # เฉย ๆ regex จะจับ match จากตำแหน่งซ้ายสุด (คำสั่ง) ไปจนถึง </draft> ตัวจริง
        # ทำให้ดึงเนื้อหาผิดทั้งก้อน — บังคับให้ tag เปิดต้องตามด้วยขึ้นบรรทัดใหม่ทันที
        # ให้ตรงกับรูปแบบที่ template ห่อจริง (<draft>\n{{ draft }}\n</draft>)
        draft_m = re.search(r"<draft>\n(.*?)\n</draft>", user_content, flags=re.DOTALL)
        draft = draft_m.group(1) if draft_m else user_content
        return draft  # mock: คืนต้นฉบับตรง ๆ (คงตัวเลข/ชื่อ/เลขอ้างอิงเดิมทุกตัวตาม spec)

    def _respond_report(self, user_content: str) -> str:
        return json.dumps(
            {
                "intro": "สัปดาห์นี้มีการแข่งขันตามตารางพรีเมียร์ลีก",
                "highlights": ["สรุปผลตามข้อมูลที่มี"],
            },
            ensure_ascii=False,
        )
