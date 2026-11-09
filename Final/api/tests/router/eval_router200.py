"""Evaluate the production router on the frozen 200-case Thai suite."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from app.core.config import get_settings
from app.core.errors import AppError
from app.infra.db import Base, create_engine, create_session_factory
from app.infra.jev import JevClient, JevFailed
from app.infra.llm import GroqClient
from app.router import llm_decision
from app.router.decide import decide
from app.router.decision import ANSWER_ROUTES

DATA = Path(__file__).with_name("router200_th.jsonl")


class NeedsProvider(Exception):
    """The offline pass reached the model boundary."""


async def evaluate(live: bool) -> dict:
    cases = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    labels = set(ANSWER_ROUTES) | {"clarify", "gap_question", "decline", "small_talk"}
    if len(cases) != 200 or len({c["id"] for c in cases}) != 200:
        raise ValueError("Expected 200 distinct case IDs")
    if {c["route"] for c in cases} != labels:
        raise ValueError("Unexpected route coverage")
    rows = []
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = create_session_factory(engine)
    settings = get_settings()
    llm = GroqClient(settings, sessions)
    jev = JevClient(settings, sessions) if live else None
    real_jev = llm_decision.ask_jev
    real_groq = llm_decision.ask_llm
    try:
        for case in cases:
            row = dict(
                id=case["id"],
                expected=case["route"],
                predicted=None,
                jev_called=False,
                jev_route=None,
                groq_called=False,
            )

            async def observe_jev(*args, row=row, **kwargs):
                row["jev_called"] = True
                try:
                    decision = await real_jev(*args, **kwargs)
                except JevFailed:
                    row["jev_failed"] = True
                    raise
                row["jev_route"] = decision.route
                return decision

            async def observe_groq(*args, row=row, **kwargs):
                if not live:
                    raise NeedsProvider
                row["groq_called"] = True
                return await real_groq(*args, **kwargs)

            with (
                patch.object(llm_decision, "ask_jev", observe_jev),
                patch.object(llm_decision, "ask_llm", observe_groq),
            ):
                try:
                    d = await decide(
                        case["message"],
                        has_profile=case["has_profile"],
                        recent=case["recent"],
                        llm=llm,
                        jev=jev,
                    )
                    row.update(predicted=d.route, layer=d.layer)
                except NeedsProvider:
                    row["status"] = "needs_provider"
                except AppError as exc:
                    row["error"] = exc.code
            rows.append(row)
    finally:
        await llm.aclose()
        if jev:
            await jev.aclose()
        await engine.dispose()
    matrix = {
        label: dict(Counter(r["predicted"] or "NO_OUTPUT" for r in rows if r["expected"] == label))
        for label in sorted(labels)
    }
    f1 = {}
    for label, counts in matrix.items():
        predicted = sum(r["predicted"] == label for r in rows)
        f1[label] = 2 * counts.get(label, 0) / (sum(counts.values()) + predicted)
    correct = sum(r["expected"] == r["predicted"] for r in rows)
    return dict(
        mode="live" if live else "offline",
        cases=len(rows),
        correct=correct,
        outputs=sum(r["predicted"] is not None for r in rows),
        accuracy=correct / len(rows) if live else None,
        macro_f1=sum(f1.values()) / len(f1) if live else None,
        jev_calls=sum(r["jev_called"] for r in rows),
        jev_outputs=sum(r["jev_route"] is not None for r in rows),
        jev_correct_before_fallback=sum(r["jev_route"] == r["expected"] for r in rows),
        groq_fallback_calls=sum(r["groq_called"] for r in rows),
        confusion=matrix,
        rows=rows,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call Jev with Groq fallback")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.live))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print({k: v for k, v in report.items() if k not in ("confusion", "rows")})
