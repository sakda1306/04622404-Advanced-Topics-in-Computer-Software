"""Smoke test against a running api on Postgres + Redis (CI and docker compose).

    API_URL=http://localhost:8000 python scripts/smoke.py

Needs the seeded accounts (SEED_ADMIN_PASSWORD / SEED_DEMO_PASSWORD) and the router
and football-data stubs, or the real services. Covers what the SQLite tests cannot:
Postgres types and constraints, Redis-backed limits and markers, the real HTTP stack.
Exits 1 on the first failed check.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "")
DEMO_PASSWORD = os.environ.get("SEED_DEMO_PASSWORD", "")


def check(name: str, ok: bool, response: httpx.Response | None = None) -> None:
    if not ok:
        detail = f" -> {response.status_code} {response.text[:300]}" if response else ""
        print(f"FAIL {name}{detail}")
        sys.exit(1)
    print(f"ok   {name}")


def is_problem(response: httpx.Response, status: int, code: str) -> bool:
    return (
        response.status_code == status
        and response.headers.get("content-type", "").startswith("application/problem+json")
        and response.json().get("code") == code
    )


def signed_in(username: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=API_URL, timeout=60)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    check(f"login {username}", response.status_code == 200, response)
    return client


def chat(client: httpx.Client, message: str, session_id: str | None = None) -> dict[str, Any]:
    response = client.post("/api/chat", json={"session_id": session_id, "message": message})
    check(f"chat {message!r}", response.status_code == 200, response)
    body: dict[str, Any] = response.json()
    return body


async def concurrent_feedback(cookies: httpx.Cookies, message_id: str) -> list[int]:
    async with httpx.AsyncClient(base_url=API_URL, cookies=cookies, timeout=30) as client:
        responses = await asyncio.gather(
            *[
                client.post("/api/feedback", json={"message_id": message_id, "rating": rating})
                for rating in (1, -1, 1, -1)
            ]
        )
    return [r.status_code for r in responses]


def main() -> None:
    anonymous = httpx.Client(base_url=API_URL, timeout=30)
    response = anonymous.get("/health")
    check("GET /health", response.json().get("status") == "ok", response)
    response = anonymous.get("/ready")
    check("GET /ready (database)", response.status_code == 200, response)

    demo = signed_in("demo1", DEMO_PASSWORD)
    first = chat(demo, "เมื่อวานปืนใหญ่ชนะไหม")
    check("Thai answer survives the round trip", "ชนะ" in first["answer"])
    follow_up = chat(demo, "อธิบายกฎล้ำหน้า", first["session_id"])
    check("follow-up stays in the session", follow_up["session_id"] == first["session_id"])

    # Right after the answer: the background write may still be running (pending marker).
    response = demo.post("/api/feedback", json={"message_id": first["message_id"], "rating": 1})
    check("feedback right after the answer", response.status_code == 200, response)
    codes = asyncio.run(concurrent_feedback(demo.cookies, follow_up["message_id"]))
    check(f"concurrent feedback on one answer {codes}", codes == [200] * len(codes))

    response = demo.get(f"/api/history/{first['session_id']}")
    messages = response.json().get("messages", [])
    check(
        "history holds both turns in order",
        [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"],
        response,
    )
    check("history keeps the rating", messages[1]["rating"] == 1, response)

    # Postgres text cannot hold U+0000: must be a 422, never a 500 or a lost turn.
    response = demo.post("/api/chat", json={"session_id": None, "message": "ปืน\u0000ใหญ่"})
    check("NUL in a message -> 422", is_problem(response, 422, "VALIDATION_ERROR"), response)
    response = demo.patch("/api/me/preferences", json={"favorite_team_id": 2**31})
    check("team id beyond INTEGER -> 422", is_problem(response, 422, "VALIDATION_ERROR"), response)
    response = demo.post("/api/feedback", json={"message_id": str(uuid.uuid4()), "rating": 1})
    check("feedback on an unknown id -> 404", is_problem(response, 404, "NOT_FOUND"), response)
    response = demo.get("/api/admin/stats")
    check("user on an admin path -> 403", is_problem(response, 403, "FORBIDDEN"), response)

    admin = signed_in("admin", ADMIN_PASSWORD)
    response = admin.get("/api/admin/stats?days=1")
    check("admin stats count the chats", response.json().get("total_messages", 0) >= 2, response)
    response = admin.get("/api/admin/logs?limit=1")
    cursor = response.json().get("next_cursor")
    check("admin logs page", response.status_code == 200 and cursor is not None, response)
    response = admin.get("/api/admin/logs", params={"limit": 1, "cursor": cursor})
    check("admin logs next page (cursor on Postgres)", response.status_code == 200, response)
    response = admin.get("/api/admin/audit")
    check("admin audit", response.status_code == 200, response)
    print("smoke passed")


if __name__ == "__main__":
    main()
