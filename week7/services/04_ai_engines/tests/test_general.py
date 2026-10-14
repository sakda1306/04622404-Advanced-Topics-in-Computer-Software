from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "engines"


def test_general_success_primary():
    with patch("app.main.call_general_ai") as mock_call:
        mock_call.return_value = ("กฎล้ำหน้าคือ...", "openai/gpt-oss-120b", {"input": 40, "output": 55})
        r = client.post(
            "/general",
            json={"request_id": "req-1", "query": "กฎล้ำหน้าคืออะไร", "history": [], "language": "th"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "general_ai"
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["sources"] == []
    assert body["data"] is None
    assert body["token_usage"] == {"input": 40, "output": 55}
    assert "latency_ms" in body


def test_general_uses_history_and_language():
    with patch("app.main.call_general_ai") as mock_call:
        mock_call.return_value = ("Offside is...", "gemini-2.0-flash", {"input": 30, "output": 40})
        r = client.post(
            "/general",
            json={
                "request_id": "req-2",
                "query": "Explain it in more detail",
                "history": [
                    {"role": "user", "content": "What is offside?"},
                    {"role": "assistant", "content": "It's a rule about..."},
                ],
                "language": "en",
            },
        )
    assert r.status_code == 200
    call_kwargs = mock_call.call_args.kwargs
    messages = call_kwargs["messages"]
    # system + 2 history + 1 user = 4
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert "English" in messages[0]["content"]
    assert messages[-1]["content"] == "Explain it in more detail"


def test_general_both_providers_down_returns_503_problem_json():
    from app.llm_client import LLMUnavailableError

    with patch("app.main.call_general_ai", side_effect=LLMUnavailableError("groq down | gemini down")):
        r = client.post(
            "/general",
            json={
                "request_id": "body-value-should-be-ignored",  # จงใจให้ต่างจาก header
                "query": "อธิบายกติกาจุดโทษ",
                "history": [],
                "language": "th",
            },
            headers={"X-Request-ID": "req-3"},
        )
    assert r.status_code == 503
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers["x-request-id"] == "req-3"
    body = r.json()
    assert body["code"] == "LLM_UNAVAILABLE"
    assert body["service"] == "engines"
    assert body["request_id"] == "req-3"


def test_general_missing_query_returns_422():
    r = client.post("/general", json={"request_id": "req-4", "language": "th"})
    assert r.status_code == 422

def test_thai_prompt_reads_questions_as_football_and_uses_the_team_note():
    from app.main import SYSTEM_PROMPT_TH

    # "ล้ำหน้า" was answered as "ahead of others" instead of offside.
    assert "ล้ำหน้า = offside" in SYSTEM_PROMPT_TH
    # The router names the club behind a nickname in this note (03 router.with_team_note).
    assert "ชื่อทีมในคำถาม" in SYSTEM_PROMPT_TH
    assert "ห้ามแต่งขึ้นเอง" in SYSTEM_PROMPT_TH
    assert "ครับ" in SYSTEM_PROMPT_TH


def test_english_prompt_uses_the_team_note():
    from app.main import SYSTEM_PROMPT_EN

    assert "Teams named in the question" in SYSTEM_PROMPT_EN
    assert "offside" in SYSTEM_PROMPT_EN
