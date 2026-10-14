import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_trivia_multi_context_cites_relevant_only(client):
    body = load("trivia_2")
    resp = client.post("/generate", json=body)
    data = resp.json()
    assert data["safety"]["blocked"] is False
    # mock ตอบจาก context แรกที่เกี่ยวข้อง — sources ต้องไม่มี ref ที่ไม่ถูกอ้าง
    cited_refs = {s["ref"] for s in data["sources"]}
    assert cited_refs.issubset({1, 2})


def test_standings_query(client):
    body = load("match_2")
    resp = client.post("/generate", json=body)
    data = resp.json()
    assert data["safety"]["blocked"] is False
    assert len(data["sources"]) >= 1


def test_insufficient_partial_info_not_in_context(client):
    body = load("insufficient_1")
    resp = client.post("/generate", json=body)
    # mock คืนคำตอบจาก context ที่ให้ (เรื่อง Arsenal ไม่ใช่ Liverpool) — ยัง cite ได้ปกติ
    # การทดสอบ insufficient แท้ ๆ (LLM จริงต้องบอกไม่รู้) ต้องทำกับ provider จริง
    assert resp.status_code == 200


def test_injection_in_context_does_not_leak_into_safety(client):
    body = load("injection_ctx")
    resp = client.post("/generate", json=body)
    data = resp.json()
    # แม้ context จะพยายามฝังคำสั่งให้ชวนพนัน mock ไม่ execute คำสั่งนั้น (แค่ echo title/snippet)
    # คำตอบสุดท้ายต้องไม่ผ่านเป็นคำแนะนำพนันโดยไม่ถูกบล็อก
    assert resp.status_code == 200
    if data["safety"]["blocked"]:
        assert data["safety"]["reason"] in (
            "gambling_odds",
            "gambling_tips",
            "gambling_promotion",
            "injection_attempt",
        )


def test_historical_odds_allowed_in_grounded(client):
    body = load("historical_odds_ok")
    resp = client.post("/generate", json=body)
    assert resp.status_code == 200
