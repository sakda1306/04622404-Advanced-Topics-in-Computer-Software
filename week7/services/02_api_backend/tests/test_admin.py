"""/api/admin/* (CONTRACT §1.1): role checks, pages, audit on every change."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.conftest import DEMO_PASSWORD, assert_problem
from tests.test_chat import ask

ADMIN_GETS = [
    "/api/admin/stats",
    "/api/admin/pipeline",
    "/api/admin/feedback",
    "/api/admin/logs",
    "/api/admin/reports",
    "/api/admin/audit",
    "/api/admin/users",
    "/api/admin/kb/stats",
]


@pytest.mark.parametrize("path", ADMIN_GETS)
async def test_user_gets_403(demo: httpx.AsyncClient, path: str) -> None:
    assert_problem(await demo.get(path), 403, "FORBIDDEN")


@pytest.mark.parametrize("path", ADMIN_GETS)
async def test_anonymous_gets_401(client: httpx.AsyncClient, path: str) -> None:
    assert_problem(await client.get(path), 401, "UNAUTHENTICATED")


async def test_user_cannot_trigger_ingest(demo: httpx.AsyncClient) -> None:
    response = await demo.post("/api/admin/pipeline/ingest", json={"scope": "all"})
    assert_problem(response, 403, "FORBIDDEN")


async def test_admin_gets_200(admin: httpx.AsyncClient) -> None:
    for path in ADMIN_GETS:
        response = await admin.get(path)
        assert response.status_code == 200, (path, response.text)


async def audit_actions(admin: httpx.AsyncClient) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (await admin.get("/api/admin/audit")).json()["items"]
    return items


async def test_stats(demo: httpx.AsyncClient, admin: httpx.AsyncClient) -> None:
    first = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    await ask(demo, "ใครได้บัลลงดอร์ 2008")
    await ask(demo, "ช่วยหาทีเด็ดพนันให้หน่อย")
    await demo.post("/api/feedback", json={"message_id": first["message_id"], "rating": -1})

    stats = (await admin.get("/api/admin/stats?days=7")).json()
    assert stats["days"] == 7
    assert stats["total_messages"] == 3
    assert stats["by_route"] == {"football_rag": 2, "decline": 1}
    assert stats["by_layer"] == {"rules": 2, "guard": 1}
    assert stats["feedback"] == {"up": 0, "down": 1}
    assert set(stats["latency_ms"]) == {"p50", "p95"}
    assert stats["fallback_count"] == 0


async def test_feedback_page_and_message_detail(
    demo: httpx.AsyncClient, admin: httpx.AsyncClient
) -> None:
    answer = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    liked = await ask(demo, "ใครได้บัลลงดอร์ 2008")
    await demo.post(
        "/api/feedback", json={"message_id": answer["message_id"], "rating": -1, "comment": "ผลผิด"}
    )
    await demo.post("/api/feedback", json={"message_id": liked["message_id"], "rating": 1})

    page = (await admin.get("/api/admin/feedback?rating=-1")).json()
    assert page["next_cursor"] is None
    [item] = page["items"]
    assert item["message_id"] == answer["message_id"]
    assert item["question"] == "เมื่อวานปืนใหญ่ชนะไหม"
    assert item["answer_preview"] == answer["answer"][:120]
    assert item["user"]["username"] == "demo1"
    assert item["comment"] == "ผลผิด"
    assert item["route"] == "football_rag"
    assert item["fallback"] is None

    detail = (await admin.get(f"/api/admin/messages/{answer['message_id']}")).json()
    assert detail["request_id"] == answer["request_id"]
    assert detail["question"] == "เมื่อวานปืนใหญ่ชนะไหม"
    assert detail["answer"] == answer["answer"]
    assert detail["trace"]["decided_at_layer"] == "rules"
    assert detail["token_usage"] == {"input": 0, "output": 0}
    assert detail["reasoning"].startswith("stub")
    assert detail["rating"] == -1
    assert detail["sources"][0]["doc_id"] == "match-2026-mw05-57-61"


async def test_feedback_pagination(demo: httpx.AsyncClient, admin: httpx.AsyncClient) -> None:
    ids = []
    for i in range(3):
        body = await ask(demo, f"q{i}")
        await demo.post("/api/feedback", json={"message_id": body["message_id"], "rating": 1})
        ids.append(body["message_id"])
    first = (await admin.get("/api/admin/feedback?limit=2")).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    second = (await admin.get(f"/api/admin/feedback?limit=2&cursor={first['next_cursor']}")).json()
    seen = [i["message_id"] for i in first["items"] + second["items"]]
    assert sorted(seen) == sorted(ids)
    assert second["next_cursor"] is None


async def test_bad_cursor_is_422(admin: httpx.AsyncClient) -> None:
    assert_problem(await admin.get("/api/admin/logs?cursor=xyz"), 422, "VALIDATION_ERROR")


async def test_logs_filters(demo: httpx.AsyncClient, admin: httpx.AsyncClient) -> None:
    ok = await ask(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    await demo.post("/api/chat", json={"message": "__error__"})
    logs = (await admin.get("/api/admin/logs")).json()["items"]
    assert {log["status"] for log in logs} == {200, 502}
    by_id = (await admin.get(f"/api/admin/logs?request_id={ok['request_id']}")).json()["items"]
    assert [log["message_id"] for log in by_id] == [ok["message_id"]]
    assert by_id[0]["decided_at_layer"] == "rules"
    by_route = (await admin.get("/api/admin/logs?route=football_rag")).json()["items"]
    assert len(by_route) == 1
    assert (await admin.get("/api/admin/logs?fallback=any")).json()["items"] == []


async def test_unknown_admin_message_is_404(admin: httpx.AsyncClient) -> None:
    response = await admin.get("/api/admin/messages/00000000-0000-0000-0000-000000000000")
    assert_problem(response, 404, "NOT_FOUND")


async def test_pipeline_and_ingest(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/api/admin/pipeline/ingest", json={"scope": "fixtures"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert response.json()["scope"] == "fixtures"

    job = (await admin.get(f"/api/admin/jobs/{job_id}")).json()
    me = (await admin.get("/api/auth/me")).json()["user"]
    # triggered_by is set by the api, never taken from the web.
    assert job["triggered_by"] == f"admin:{me['id']}"

    pipeline = (await admin.get("/api/admin/pipeline")).json()
    assert pipeline["status"]["current_season"] == "2026"
    assert pipeline["jobs"][0]["job_id"] == job_id

    [entry, *_] = await audit_actions(admin)
    assert entry["action"] == "pipeline.ingest"
    assert entry["target"] == "fixtures"
    assert entry["detail"]["after"]["job_id"] == job_id
    assert entry["actor"]["username"] == "admin"


async def test_ingest_scope_is_validated(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/api/admin/pipeline/ingest", json={"scope": "everything"})
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_generate_report(admin: httpx.AsyncClient) -> None:
    response = await admin.post(
        "/api/admin/reports/generate", json={"season": "2026", "matchweek": 5}
    )
    assert response.status_code == 202
    [entry, *_] = await audit_actions(admin)
    assert entry["action"] == "report.generate"
    assert entry["target"] == "weekly-2026-mw05"


async def test_report_review_flow(admin: httpx.AsyncClient) -> None:
    drafts = (await admin.get("/api/admin/reports?status=draft")).json()["items"]
    assert drafts[0]["matchweek"] == 5

    edited = await admin.patch("/api/admin/reports/2026/5", json={"title": "หัวข้อใหม่"})
    assert edited.status_code == 200
    assert edited.json()["title"] == "หัวข้อใหม่"

    published = await admin.post("/api/admin/reports/2026/5/publish")
    assert published.json()["status"] == "published"

    # Published reports cannot be edited until they are unpublished.
    response = await admin.patch("/api/admin/reports/2026/5", json={"title": "อีกรอบ"})
    assert_problem(response, 409, "REPORT_NOT_EDITABLE")

    unpublished = await admin.post("/api/admin/reports/2026/5/unpublish")
    assert unpublished.json()["status"] == "unpublished"

    actions = [e["action"] for e in await audit_actions(admin)]
    assert actions[:3] == ["report.unpublish", "report.publish", "report.edit"]
    publish_entry = (await audit_actions(admin))[1]
    assert publish_entry["detail"]["before"]["status"] == "draft"
    assert publish_entry["detail"]["after"]["status"] == "published"


async def test_report_patch_needs_a_field(admin: httpx.AsyncClient) -> None:
    assert_problem(await admin.patch("/api/admin/reports/2026/5", json={}), 422, "VALIDATION_ERROR")


async def test_unknown_report_is_404(admin: httpx.AsyncClient) -> None:
    assert_problem(await admin.get("/api/admin/reports/2026/30"), 404, "NOT_FOUND")


async def test_admin_cannot_modify_self(admin: httpx.AsyncClient) -> None:
    me = (await admin.get("/api/auth/me")).json()["user"]
    response = await admin.patch(f"/api/admin/users/{me['id']}", json={"disabled": True})
    assert_problem(response, 409, "CANNOT_MODIFY_SELF")


async def test_disable_user(
    admin: httpx.AsyncClient, demo: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    await ask(demo, "hello")
    users = (await admin.get("/api/admin/users?q=demo1")).json()["items"]
    [demo_user] = users
    assert demo_user["message_count"] == 1

    response = await admin.patch(f"/api/admin/users/{demo_user['id']}", json={"disabled": True})
    assert response.json()["disabled"] is True
    # The existing cookie stops working at once, and login is refused.
    assert_problem(await demo.get("/api/auth/me"), 401, "ACCOUNT_DISABLED")
    login = await client.post(
        "/api/auth/login", json={"username": "demo1", "password": DEMO_PASSWORD}
    )
    assert_problem(login, 401, "ACCOUNT_DISABLED")

    [entry, *_] = await audit_actions(admin)
    assert entry["action"] == "user.update"
    assert entry["detail"] == {
        "before": {"role": "user", "disabled": False},
        "after": {"role": "user", "disabled": True},
    }


async def test_promoted_user_gets_admin_access(
    admin: httpx.AsyncClient, demo: httpx.AsyncClient
) -> None:
    [demo_user] = (await admin.get("/api/admin/users?q=demo1")).json()["items"]
    await admin.patch(f"/api/admin/users/{demo_user['id']}", json={"role": "admin"})
    assert (await demo.get("/api/admin/stats")).status_code == 200


async def test_kb_delete_and_reindex(admin: httpx.AsyncClient) -> None:
    stats = (await admin.get("/api/admin/kb/stats")).json()
    assert stats["documents"] >= 1
    response = await admin.delete("/api/admin/kb/documents/standings-2026-mw05")
    assert response.json() == {"deleted": True}
    response = await admin.delete("/api/admin/kb/documents/standings-2026-mw05")
    assert response.json() == {"deleted": False}
    response = await admin.post("/api/admin/kb/reindex", json={"category": "trivia"})
    assert response.status_code == 202
    actions = [e["action"] for e in await audit_actions(admin)]
    assert actions[:3] == ["kb.reindex", "kb.delete", "kb.delete"]


async def test_reindex_accepts_the_player_category(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/api/admin/kb/reindex", json={"category": "player"})
    assert response.status_code == 202
    entry = (await audit_actions(admin))[0]
    assert (entry["action"], entry["target"]) == ("kb.reindex", "player")


async def test_reindex_accepts_the_historical_category(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/api/admin/kb/reindex", json={"category": "historical"})
    assert response.status_code == 202
    entry = (await audit_actions(admin))[0]
    assert (entry["action"], entry["target"]) == ("kb.reindex", "historical")


async def test_reindex_still_rejects_unknown_categories(admin: httpx.AsyncClient) -> None:
    response = await admin.post("/api/admin/kb/reindex", json={"category": "news"})
    assert response.status_code == 422


async def test_audit_filter_by_action(admin: httpx.AsyncClient) -> None:
    await admin.post("/api/admin/pipeline/ingest", json={"scope": "all"})
    await admin.post("/api/admin/reports/generate", json={})
    items = (await admin.get("/api/admin/audit?action=report.generate")).json()["items"]
    assert [i["action"] for i in items] == ["report.generate"]
    assert items[0]["target"] == "weekly-latest"
