import json

import httpx
import pytest

from decision_engine.config import Settings
from decision_engine.models import Action
from decision_engine.provider import GeminiExplanationProvider


@pytest.mark.asyncio
async def test_gemini_provider_generate_success(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_model_explainer="gemini-2.0-flash",
        llm_api_key="mock-key",
    )
    provider = GeminiExplanationProvider(settings)

    mock_candidate_output = {
        "action_code": "CAUTION",
        "summary": "เส้นทางมีความเสี่ยงปานกลางจากฝนตกและน้ำท่วมขัง ควรใช้ความระมัดระวัง",
        "reasons": ["ฝนตกหนักช่วงบางเขน", "น้ำท่วมขังผิวจราจร"],
        "instructions": ["ลดความเร็วลงเหลือไม่เกิน 60 กม./ชม.", "เปิดไฟหน้ารถ"],
        "uncertainty": [],
        "evidence_ids": ["ev-1", "ev-2"],
    }

    async def mock_post(self, url, **kwargs):
        assert "key=" not in str(url)
        assert "gemini-2.0-flash" in str(url)
        assert kwargs["headers"]["x-goog-api-key"] == "mock-key"
        payload = kwargs.get("json", {})
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(mock_candidate_output)}]}}
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    package = {
        "locked_action": "CAUTION",
        "evidence_ids": ["ev-1", "ev-2"],
        "sentence_bank": {
            "summary": "ข้อความสำรอง",
            "reasons": ["เหตุผล"],
            "instructions": ["คำแนะนำ"],
            "uncertainty": [],
        },
        "output_schema": {},
    }

    result = await provider.generate(package, max_output_tokens=1500)
    assert result["action_code"] == "CAUTION"
    assert result["summary"] == mock_candidate_output["summary"]
    assert result["evidence_ids"] == ["ev-1", "ev-2"]


@pytest.mark.asyncio
async def test_gemini_provider_error_raises(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_model_explainer="gemini-2.0-flash",
        llm_api_key="mock-key",
    )
    provider = GeminiExplanationProvider(settings)

    async def mock_post_fail(self, url, **kwargs):
        return httpx.Response(status_code=500, text="Internal Server Error")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_fail)

    package = {
        "locked_action": "CAUTION",
        "evidence_ids": [],
        "sentence_bank": {},
        "output_schema": {},
    }

    with pytest.raises(RuntimeError):
        await provider.generate(package, max_output_tokens=1500)


@pytest.mark.asyncio
async def test_explain_with_gemini_natural_language(monkeypatch, samples):
    from decision_engine.explanation import explain
    from decision_engine.policy import Decision

    settings = Settings(
        _env_file=None,
        llm_model_explainer="gemini-2.0-flash",
        llm_api_key="mock-key",
    )
    provider = GeminiExplanationProvider(settings)

    mock_candidate_output = {
        "action_code": "AVOID",
        "summary": "เส้นทางมีความเสี่ยงสูงมากเนื่องจากมีน้ำท่วมสูงและปิดถนน แนะนำหลีกเลี่ยงการเดินทาง",
        "reasons": ["น้ำท่วมผิวจราจร 40 ซม.", "เส้นทางหลักถูกสั่งปิดชั่วคราว"],
        "instructions": ["หลีกเลี่ยงการเดินทางผ่านเส้นทางนี้โดยเด็ดขาด", "ติดตามประกาศจาก ปภ."],
        "uncertainty": [],
        "evidence_ids": ["ev-flood-1"],
    }

    async def mock_post(self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(mock_candidate_output)}]}}
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    decision = Decision(
        action=Action.AVOID,
        confidence="HIGH",
        confidence_details=None,
        rule_id="HIGH_RISK",
        escalation_required=False,
        issues=(),
        selected_route_id=None,
        suggested_departure_time=None,
    )
    from decision_engine.models import DecisionRequest

    request = DecisionRequest.model_validate(samples["high_risk"])

    explanation, checks = await explain(
        decision, request, settings, provider, citation_ids=["ev-flood-1"]
    )
    assert explanation.mode == "provider"
    assert explanation.summary == mock_candidate_output["summary"]
    assert "LLM_OUTPUT_VALIDATED" in checks
