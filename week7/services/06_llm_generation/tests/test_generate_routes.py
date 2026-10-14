import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_trivia_th_answer_cites(client):
    body = load("trivia_1")
    resp = client.post("/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety"]["blocked"] is False
    assert "[1]" in data["answer"]
    assert data["sources"][0]["ref"] == 1
    assert resp.headers["X-Request-ID"] == body["request_id"]


def test_match_report_grounded(client):
    body = load("match_1")
    resp = client.post("/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety"]["blocked"] is False
    assert len(data["sources"]) >= 1


def test_gambling_query_blocked_no_llm_call(client):
    body = load("gambling_query")
    resp = client.post("/generate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety"]["blocked"] is True
    assert data["safety"]["reason"] == "gambling_request"
    assert data["model"] == "none"
    assert data["token_usage"] == {"input": 0, "output": 0}


def test_empty_contexts_insufficient(client):
    body = {
        "request_id": "44444444-4444-4444-4444-444444444444",
        "mode": "grounded",
        "query": "แมนยูเมื่อวานเจอใคร",
        "language": "th",
        "contexts": [],
        "history": [],
    }
    resp = client.post("/generate", json=body)
    data = resp.json()
    assert "ไม่พบข้อมูลที่เพียงพอ" in data["answer"]
    assert data["sources"] == []
    assert data["model"] == "none"


def test_duplicate_ref_422(client):
    body = {
        "mode": "grounded",
        "query": "test",
        "language": "th",
        "contexts": [
            {"ref": 1, "text": "a", "source": {"ref": 1}},
            {"ref": 1, "text": "b", "source": {"ref": 1}},
        ],
    }
    resp = client.post("/generate", json=body)
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["code"] == "VALIDATION_ERROR"


def test_passthrough_draft_empty_422(client):
    resp = client.post(
        "/generate",
        json={"mode": "passthrough", "query": "", "language": "th", "draft": ""},
    )
    assert resp.status_code == 422


def test_passthrough_same_language_no_llm_call(client):
    resp = client.post(
        "/generate",
        json={
            "mode": "passthrough",
            "query": "",
            "language": "th",
            "draft": "อาร์เซนอลชนะเชลซี 2-1 เมื่อวานนี้ที่เอมิเรตส์สเตเดียม",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "none"
    assert data["sources"] == []


def test_passthrough_gambling_blocked(client):
    resp = client.post(
        "/generate",
        json={
            "mode": "passthrough",
            "query": "",
            "language": "th",
            "draft": "วันนี้ควรแทงทีมนี้เลย เดี๋ยวรวย",
        },
    )
    data = resp.json()
    assert data["safety"]["blocked"] is True


def test_passthrough_translate_extracts_draft_not_whole_prompt(client):
    """mock ต้องดึงเฉพาะเนื้อ <draft> จริง ไม่ใช่ทั้งก้อน system/user prompt
    (เคยมีบั๊ก: คำว่า "<draft>" ที่โผล่ในประโยคคำสั่งเองทำให้ regex จับผิดตำแหน่ง)
    """
    draft = "Arsenal won 2-1 against Chelsea yesterday at the Emirates."
    resp = client.post(
        "/generate",
        json={"mode": "passthrough", "query": "", "language": "th", "draft": draft},
    )
    assert resp.status_code == 200
    data = resp.json()
    # mock คืน draft เดิมตรง ๆ (คงตัวเลข/ชื่อ/เลขอ้างอิงเดิม) — ต้องไม่ปนคำสั่งระบบ
    assert data["answer"].strip() == draft
    assert "รักษาความหมายเดิม" not in data["answer"]
    assert "ตอบเฉพาะข้อความที่แปลแล้ว" not in data["answer"]


def test_extra_field_ignored(client):
    body = load("trivia_1")
    body["some_new_optional_field"] = "hello"
    resp = client.post("/generate", json=body)
    assert resp.status_code == 200


def test_422_is_problem_json_not_fastapi_default(client):
    resp = client.post("/generate", json={"mode": "unknown_mode"})
    assert resp.status_code == 422
    body = resp.json()
    assert "code" in body and "type" in body and "detail" in body
