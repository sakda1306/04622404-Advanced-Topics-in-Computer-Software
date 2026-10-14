"""Smoke test against a running retrieval service with the real model and trivia file.

    RETRIEVAL_URL=http://localhost:8000 python scripts/smoke.py

Waits for /ready, then checks the CONTRACT §4 shape on the real knowledge base, and the
§6 index round trip (upsert -> search -> rebuild -> delete) with a document it removes again.
Exits 1 on the first failed check.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import httpx

URL = os.environ.get("RETRIEVAL_URL", "http://localhost:8000")
FIRST_QUESTION = (
    "It is alleged that this country 'sold out' to Argentina in a 1978 World Cup Group 2 game."
)
SMOKE_DOC = {
    "doc_id": "match-2026-mw38-9001-9002",
    "title": "Smoke Rovers 7-3 Probe Albion",
    "text": "Smoke Rovers 7-3 Probe Albion. Zyxwv scored four goals at Checkpoint Park.",
    "category": "match_report",
    "origin": "api-football",
    "season": "2026",
    "matchweek": 38,
    "team_ids": [9001, 9002],
    "date": "2026-09-25",
}


def check(name: str, ok: bool, response: httpx.Response | None = None) -> None:
    if not ok:
        detail = f" -> {response.status_code} {response.text[:300]}" if response else ""
        print(f"FAIL {name}{detail}")
        sys.exit(1)
    print(f"ok   {name}")


def wait_ready(client: httpx.Client, seconds: int = 180) -> httpx.Response:
    deadline = time.monotonic() + seconds
    while True:
        try:
            response = client.get("/ready")
            if response.status_code == 200 or time.monotonic() > deadline:
                return response
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
        time.sleep(2)


def search(client: httpx.Client, **body: Any) -> httpx.Response:
    return client.post("/search", json=body)


def main() -> None:
    client = httpx.Client(base_url=URL, timeout=30)
    # Waited for first: the port opens only after the embedding model has loaded.
    response = wait_ready(client)
    check("GET /ready", response.status_code == 200 and response.json()["chunks"] > 1900, response)
    response = client.get("/health")
    check("GET /health", response.json().get("service") == "retrieval", response)

    for mode in ("hybrid", "bm25", "vector"):
        response = search(client, query=FIRST_QUESTION, mode=mode)
        chunks = response.json().get("chunks", [])
        check(
            f"{mode}: the question finds trivia-0001 first",
            response.status_code == 200 and chunks[0]["source"]["doc_id"] == "trivia-0001",
            response,
        )

    response = search(client, query="Who won", filters={"category": ["match_report"]})
    check("no live documents yet -> 200 and []", response.json().get("chunks") == [], response)
    response = search(client, query="Arsenal", top_k=0)
    check(
        "top_k 0 -> 422 Problem-JSON",
        response.status_code == 422 and response.json().get("service") == "retrieval",
        response,
    )

    index_round_trip(client)
    print("smoke passed")


def found(client: httpx.Client, query: str) -> list[str]:
    response = search(client, query=query, mode="bm25", top_k=20)
    return [c["source"]["doc_id"] for c in response.json().get("chunks", [])]


def wait_job(client: httpx.Client, job_id: str, seconds: int = 120) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    while True:
        job: dict[str, Any] = client.get(f"/index/jobs/{job_id}").json()
        if job.get("status") in ("done", "failed") or time.monotonic() > deadline:
            return job
        time.sleep(1)


def index_round_trip(client: httpx.Client) -> None:
    doc_id = SMOKE_DOC["doc_id"]
    client.delete(f"/index/{doc_id}")  # left over from an interrupted run
    before = client.get("/index/stats").json()

    response = client.post("/index/upsert", json={"documents": [SMOKE_DOC]})
    check("POST /index/upsert", response.status_code == 200 and response.json()["upserted"] == 1)
    check("the upserted document is found", doc_id in found(client, "Zyxwv Checkpoint Park"))
    stats = client.get("/index/stats").json()
    check("GET /index/stats counts it", stats["documents"] == before["documents"] + 1)

    response = client.post("/index/rebuild", json={"category": "match_report"})
    check("POST /index/rebuild -> 202", response.status_code == 202, response)
    job = wait_job(client, response.json()["job_id"])
    check("the rebuild job is done", job.get("status") == "done")
    check("still found after the rebuild", doc_id in found(client, "Zyxwv Checkpoint Park"))

    response = client.delete(f"/index/{doc_id}")
    check("DELETE /index/{doc_id}", response.json() == {"deleted": True}, response)
    check("the deleted document is gone", doc_id not in found(client, "Zyxwv Checkpoint Park"))
    response = client.delete(f"/index/{doc_id}")
    check("deleting again -> deleted false", response.json() == {"deleted": False}, response)
    after = client.get("/index/stats").json()
    check("stats are back", after["documents"] == before["documents"])
    check("stats by category are back", after["by_category"] == before["by_category"])


if __name__ == "__main__":
    main()
