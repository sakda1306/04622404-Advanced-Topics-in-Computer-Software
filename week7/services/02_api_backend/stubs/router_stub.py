"""Stub of 03 router (CONTRACT §2) for local development and tests.

    uvicorn stubs.router_stub:app --port 8003

Picks a route from keywords and answers with canned text in the contract shape.
Special messages for testing the api: "__slow__" sleeps 50s, "__error__" answers 500.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="router stub")

_FETCHED_AT = "2026-09-21T09:00:00+07:00"

_MATCH_SOURCE = {
    "ref": 1,
    "doc_id": "match-2026-mw05-57-61",
    "title": "Arsenal 2–1 Chelsea · PL 2026/27 นัดที่ 5",
    "category": "match_report",
    "origin": "football-data.org",
    "season": "2026",
    "matchweek": 5,
    "team_ids": [57, 61],
    "fetched_at": _FETCHED_AT,
    "url": None,
}
_TRIVIA_SOURCE = {
    "ref": 1,
    "doc_id": "trivia-0042",
    "title": "Ballon d'Or 2008",
    "category": "trivia",
    "origin": "kb",
    "season": None,
    "matchweek": None,
    "team_ids": [],
    "fetched_at": None,
    "url": None,
}

_ANSWERS: dict[str, dict[str, Any]] = {
    "match": {
        "answer": "Arsenal ชนะ Chelsea 2–1 ในนัดที่ 5 [1]",
        "sources": [_MATCH_SOURCE],
        "route": "football_rag",
        "engines_used": ["retrieval", "generation"],
        "intent": "match_result",
    },
    "trivia": {
        "answer": "Cristiano Ronaldo ได้บัลลงดอร์ปี 2008 [1]",
        "sources": [_TRIVIA_SOURCE],
        "route": "football_rag",
        "engines_used": ["retrieval", "generation"],
        "intent": "trivia_history",
    },
    "general": {
        "answer": "ล้ำหน้าคือการที่ผู้เล่นฝ่ายรุกอยู่ใกล้เส้นประตูมากกว่าลูกบอลและผู้เล่นฝ่ายรับคนรองสุดท้าย",
        "sources": [],
        "route": "general_ai",
        "engines_used": ["general_ai", "generation"],
        "intent": "general_football",
    },
    "predict": {
        "answer": "ฟีเจอร์ทำนายผลยังไม่เปิดใช้งาน",
        "sources": [],
        "route": "local_ai",
        "engines_used": ["local_ai"],
        "intent": "prediction",
    },
    "clarify": {
        "answer": "หมายถึงยูไนเต็ดทีมไหนครับ แมนยู นิวคาสเซิล หรือเวสต์แฮม?",
        "sources": [],
        "route": "clarify",
        "engines_used": [],
        "intent": None,
    },
    "decline": {
        "answer": "ขออภัย ระบบตอบได้เฉพาะเรื่องฟุตบอลพรีเมียร์ลีก และไม่ให้ทีเด็ดพนัน",
        "sources": [],
        "route": "decline",
        "engines_used": [],
        "intent": "out_of_scope",
    },
    "chat": {
        "answer": "สวัสดีครับ ผมคือผู้ช่วยฟุตบอล ถามเรื่องพรีเมียร์ลีกได้เลยครับ",
        "sources": [],
        "route": "chat",
        "engines_used": [],
        "intent": "chitchat",
    },
}

_KEYWORDS = (
    ("decline", ("พนัน", "ทีเด็ด", "ราคาบอล", "bet", "code")),
    ("predict", ("ใครน่าจะชนะ", "ทำนาย", "predict")),
    ("clarify", ("ยูไนเต็ด", "united")),
    ("trivia", ("บัลลงดอร์", "ballon", "ประวัติ", "แชมป์")),
    ("general", ("กฎ", "ล้ำหน้า", "offside", "อธิบาย")),
    ("chat", ("สวัสดี", "ขอบคุณ", "คุณชื่ออะไร")),
)


def _pick(query: str) -> str:
    lowered = query.lower()
    for key, words in _KEYWORDS:
        if any(word in lowered for word in words):
            return key
    return "match"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "router", "version": "stub"}


@app.post("/route", response_model=None)
async def route(request: Request) -> dict[str, Any] | JSONResponse:
    started = time.perf_counter()
    body = await request.json()
    query = str(body.get("query", ""))
    if query == "__error__":
        return JSONResponse({"code": "INTERNAL_ERROR", "status": 500}, status_code=500)
    if query == "__slow__":
        await asyncio.sleep(50)
    key = _pick(query)
    canned = _ANSWERS[key]
    layer = "guard" if key == "decline" else "rules"
    return {
        "request_id": body.get("request_id"),
        "answer": canned["answer"],
        "sources": canned["sources"],
        "route": canned["route"],
        "engines_used": canned["engines_used"],
        "confidence": 0.9,
        "reasoning": f"stub: keyword match → {key}",
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "token_usage": {"input": 0, "output": 0},
        "trace": {
            "decided_at_layer": layer,
            "intent": canned["intent"],
            "rewritten_query": None,
            "filters": None,
            "fallback": None,
            "steps": [{"name": f"router.{layer}", "ms": 1}],
        },
    }
