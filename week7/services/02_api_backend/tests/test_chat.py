"""/api/chat, sessions, history, feedback (CONTRACT §1) and the router call (§2)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

from app.api.deps import Container
from app.response_log.recorder import mark_pending
from tests.conftest import RecordingRouter, assert_problem

CHAT_FIELDS = {
    "request_id",
    "session_id",
    "message_id",
    "answer",
    "sources",
    "route",
    "engines_used",
    "confidence",
    "latency_ms",
    "data_as_of",
    "created_at",
    "trace",
}


async def ask(client: httpx.AsyncClient, message: str, session_id: str | None = None) -> Any:
    response = await client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert response.status_code == 200, response.text
    return response.json()


async def test_chat_answer_matches_contract(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    assert set(body) == CHAT_FIELDS
    assert body["route"] == "football_rag"
    assert body["engines_used"] == ["retrieval", "generation"]
    assert body["confidence"] == 0.9
    assert body["sources"][0]["doc_id"] == "match-2026-mw05-57-61"
    # Oldest fetched_at among live-data sources.
    assert body["data_as_of"] == "2026-09-21T09:00:00+07:00"
    assert body["created_at"].endswith("+07:00")
    assert body["trace"]["decided_at_layer"] == "rules"


async def test_trivia_answer_has_no_data_as_of(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "ใครได้บัลลงดอร์ 2008")
    assert body["sources"][0]["origin"] == "kb"
    assert body["data_as_of"] is None


async def test_request_to_router_matches_contract(
    demo: httpx.AsyncClient, recording_router: RecordingRouter
) -> None:
    response = await demo.post(
        "/api/chat", json={"message": "เมื่อวานปืนใหญ่ชนะไหม"}, headers={"X-Request-ID": "req-1"}
    )
    body = response.json()
    sent = recording_router.requests[-1]
    assert sent["request_id"] == "req-1" == body["request_id"]
    assert sent["session_id"] == body["session_id"]
    assert sent["query"] == "เมื่อวานปืนใหญ่ชนะไหม"
    assert sent["history"] == []
    assert sent["user"]["language"] == "th"
    # From the football-data stub's /football/status.
    assert sent["context"]["season"] == "2026"
    assert sent["context"]["current_matchweek"] == 6
    assert sent["context"]["now"].endswith("+07:00")
    assert sent["context"]["last_ingest_at"] == "2026-09-21T09:00:00+07:00"


async def test_follow_up_sends_history(
    demo: httpx.AsyncClient, recording_router: RecordingRouter
) -> None:
    first = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    await ask(demo, "แล้วนัดก่อนหน้าล่ะ", first["session_id"])
    history = recording_router.requests[-1]["history"]
    assert history == [
        {"role": "user", "content": "เมื่อวานปืนใหญ่ชนะไหม"},
        {"role": "assistant", "content": first["answer"]},
    ]


@pytest.mark.parametrize("settings_overrides", [{"history_limit": 3}])
async def test_history_sent_to_router_is_capped(
    demo: httpx.AsyncClient, recording_router: RecordingRouter
) -> None:
    session_id = (await ask(demo, "q1"))["session_id"]
    await ask(demo, "q2", session_id)
    await ask(demo, "q3", session_id)
    history = recording_router.requests[-1]["history"]
    assert [m["content"] for m in history if m["role"] == "user"] == ["q2"]
    assert len(history) == 3


async def test_sessions_and_history(demo: httpx.AsyncClient) -> None:
    first = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    await ask(demo, "ใครได้บัลลงดอร์ 2008", first["session_id"])
    other = await ask(demo, "อธิบายกฎล้ำหน้า")

    sessions = (await demo.get("/api/sessions")).json()["sessions"]
    assert [s["session_id"] for s in sessions] == [other["session_id"], first["session_id"]]
    assert sessions[1]["title"] == "เมื่อวานปืนใหญ่ชนะไหม"

    history = (await demo.get(f"/api/history/{first['session_id']}")).json()
    assert history["session_id"] == first["session_id"]
    roles = [m["role"] for m in history["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    answer = history["messages"][1]
    assert answer["message_id"] == first["message_id"]
    assert answer["route"] == "football_rag"
    assert answer["rating"] is None
    assert answer["sources"][0]["ref"] == 1

    limited = (await demo.get(f"/api/history/{first['session_id']}?limit=2")).json()
    assert [m["role"] for m in limited["messages"]] == ["user", "assistant"]
    assert limited["messages"][0]["content"] == "ใครได้บัลลงดอร์ 2008"


async def test_history_of_someone_else_is_404(
    demo: httpx.AsyncClient, demo2: httpx.AsyncClient
) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    assert_problem(await demo2.get(f"/api/history/{body['session_id']}"), 404, "NOT_FOUND")
    response = await demo2.post(
        "/api/chat", json={"session_id": body["session_id"], "message": "hi"}
    )
    assert_problem(response, 404, "NOT_FOUND")


@pytest.mark.parametrize("message", ["", "   ", "x" * 2001])
async def test_message_validation(demo: httpx.AsyncClient, message: str) -> None:
    response = await demo.post("/api/chat", json={"message": message})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_chat_requires_login(client: httpx.AsyncClient) -> None:
    assert_problem(await client.post("/api/chat", json={"message": "hi"}), 401, "UNAUTHENTICATED")


@pytest.mark.parametrize("settings_overrides", [{"chat_rate_limit_per_minute": 2}])
async def test_chat_rate_limit(demo: httpx.AsyncClient) -> None:
    await ask(demo, "q1")
    await ask(demo, "q2")
    response = await demo.post("/api/chat", json={"message": "q3"})
    assert_problem(response, 429, "RATE_LIMITED")
    assert int(response.headers["retry-after"]) >= 1


async def test_router_error_is_502_and_logged(
    demo: httpx.AsyncClient, admin: httpx.AsyncClient
) -> None:
    response = await demo.post("/api/chat", json={"message": "__error__"})
    body = assert_problem(response, 502, "ROUTER_UNAVAILABLE")
    logs = (await admin.get(f"/api/admin/logs?request_id={body['request_id']}")).json()
    assert logs["items"][0]["status"] == 502
    assert logs["items"][0]["error_code"] == "ROUTER_UNAVAILABLE"
    # A failed first question leaves no empty chat behind.
    assert (await demo.get("/api/sessions")).json()["sessions"] == []


@pytest.mark.parametrize("settings_overrides", [{"router_timeout_seconds": 0.3}])
async def test_router_timeout_is_504(demo: httpx.AsyncClient) -> None:
    response = await demo.post("/api/chat", json={"message": "__slow__"})
    assert_problem(response, 504, "ROUTER_TIMEOUT")


@pytest.mark.parametrize("football_transport", [httpx.MockTransport(lambda r: httpx.Response(500))])
async def test_chat_works_when_football_data_is_down(
    demo: httpx.AsyncClient, recording_router: RecordingRouter
) -> None:
    await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    context = recording_router.requests[-1]["context"]
    assert context["current_matchweek"] is None
    assert context["last_ingest_at"] is None
    assert len(context["season"]) == 4


# ------------------------------------------------------------------ feedback


async def test_feedback_is_saved_and_shown_in_history(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    response = await demo.post(
        "/api/feedback", json={"message_id": body["message_id"], "rating": -1, "comment": "ผลผิด"}
    )
    assert response.json() == {"ok": True}
    # A second rating replaces the first.
    await demo.post("/api/feedback", json={"message_id": body["message_id"], "rating": 1})
    history = (await demo.get(f"/api/history/{body['session_id']}")).json()
    assert history["messages"][1]["rating"] == 1


async def test_feedback_on_unknown_message_is_404(demo: httpx.AsyncClient) -> None:
    response = await demo.post("/api/feedback", json={"message_id": str(uuid.uuid4()), "rating": 1})
    assert_problem(response, 404, "NOT_FOUND")


async def test_feedback_on_someone_elses_message_is_404(
    demo: httpx.AsyncClient, demo2: httpx.AsyncClient
) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    response = await demo2.post(
        "/api/feedback", json={"message_id": body["message_id"], "rating": 1}
    )
    assert_problem(response, 404, "NOT_FOUND")


async def test_feedback_before_log_is_written_is_409(
    demo: httpx.AsyncClient, container: Container
) -> None:
    me = (await demo.get("/api/auth/me")).json()["user"]
    message_id = uuid.uuid4()
    await mark_pending(container.store, message_id, uuid.UUID(me["id"]))
    response = await demo.post("/api/feedback", json={"message_id": str(message_id), "rating": 1})
    assert_problem(response, 409, "MESSAGE_NOT_READY")


async def test_feedback_rating_must_be_plus_or_minus_one(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    response = await demo.post(
        "/api/feedback", json={"message_id": body["message_id"], "rating": 0}
    )
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_chat_route_answer_has_no_sources_or_engines(demo: httpx.AsyncClient) -> None:
    body = await ask(demo, "สวัสดีครับ")
    assert body["route"] == "chat"
    assert body["engines_used"] == []
    assert body["sources"] == []
    assert body["data_as_of"] is None
    assert body["trace"]["intent"] == "chitchat"
