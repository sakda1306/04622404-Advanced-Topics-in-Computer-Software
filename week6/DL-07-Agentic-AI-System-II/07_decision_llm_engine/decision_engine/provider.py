import json
import logging

import httpx

from .config import Settings

log = logging.getLogger("decision_engine.provider")


class GeminiExplanationProvider:
    """Gemini REST provider for a structured natural-language explanation."""

    is_natural_language: bool = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.llm_api_key.get_secret_value()
        self._model = settings.llm_model_explainer
        self._base_url = settings.gemini_api_base.rstrip("/")

    async def generate(self, package: dict, *, max_output_tokens: int) -> dict:
        url = f"{self._base_url}/models/{self._model}:generateContent"

        system_instruction = (
            "คุณคือผู้ช่วยประเมินความปลอดภัยในการเดินทางอัจฉริยะ (Travel Safety Explainer) "
            "มีหน้าที่เขียนคำอธิบายสภาพเส้นทางและความปลอดภัยในการเดินทางภาษาไทยที่ถูกต้อง กระชับ สละสลวย "
            "และเป็นธรรมชาติ โดยอ้างอิงจากข้อมูลหลักฐานจริงเท่านั้น "
            "กฎเหล็ก: "
            "1. ห้ามเปลี่ยนแปลงหรือลดทอน Action Code ที่ระบบตัดสินใจไว้โดยเด็ดขาด "
            "2. ห้ามกุตัวเลขอุบัติเหตุ ปริมาณน้ำฝน หรือข้อมูลที่ไม่มีในบริบท "
            "3. รหัส evidence_ids ต้องเลือกเฉพาะรหัสที่มีอยู่ในรายการ evidence_ids ที่กำหนดให้เท่านั้น "
            "4. ตอบกลับเฉพาะข้อมูล JSON ตาม Schema ที่กำหนด"
        )

        user_prompt = (
            f"Locked Action: {package.get('locked_action')}\n"
            "Valid Evidence IDs: "
            f"{json.dumps(package.get('evidence_ids', []), ensure_ascii=False)}\n"
            "Fallback Sentence Reference: "
            f"{json.dumps(package.get('sentence_bank', {}), ensure_ascii=False)}\n"
        )
        if "context_summary" in package:
            user_prompt += (
                f"Context Details: {json.dumps(package['context_summary'], ensure_ascii=False)}\n"
            )

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

        if package.get("output_schema"):
            payload["generationConfig"]["responseSchema"] = package["output_schema"]

        timeout = httpx.Timeout(self._settings.llm_timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self._api_key},
                json=payload,
            )
            if resp.status_code != 200:
                log.warning("Gemini API error status %s", resp.status_code)
                raise RuntimeError(f"Gemini API returned status {resp.status_code}")

            data = resp.json()
            try:
                candidate = data["candidates"][0]
                text = candidate["content"]["parts"][0]["text"]
                return json.loads(text)
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                log.warning("Failed to parse Gemini response: %s", e)
                raise RuntimeError("Invalid response structure from Gemini API") from e
