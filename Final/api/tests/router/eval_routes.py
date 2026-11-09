"""Router accuracy on the Thai evaluation set, for the report (Design.md §4.6).

Calls the real Groq API for messages the rules leave open, and spends tokens. Not a pytest test.
Run from the repo root, where `.env` is: PYTHONPATH=api python -m tests.router.eval_routes

`routing_cases.jsonl` is the set the rules and prompt were tuned on. `routing_heldout.jsonl` is for
measuring only: add `heldout` to the command, and do not change the router to fit its results.

Once a set has led to a fix it is no longer held out. Keep it as `routing_heldout_v<n>.jsonl`, which
shows before and after on the same cases, and write a new one. Add `v1` to run the first such set.
Add `jev` to route with Jev (needs TYPESAFE_API_KEY, spends a little money), with Groq behind it.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import AppError
from app.infra.db import Base, create_engine, create_session_factory
from app.infra.jev import JevClient
from app.infra.llm import GroqClient
from app.infra.models import LlmCall
from app.router.decide import decide

SETS = {
    "tuned": "routing_cases.jsonl",
    "heldout": "routing_heldout.jsonl",
    "v1": "routing_heldout_v1.jsonl",
}


async def evaluate(name: str, *, use_jev: bool = False) -> None:
    path = Path(__file__).with_name(SETS[name])
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        url = f"sqlite+aiosqlite:///{Path(folder).as_posix()}/eval.db"
        engine = create_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = create_session_factory(engine)
        llm = GroqClient(get_settings(), sessions)
        jev = JevClient(get_settings(), sessions) if use_jev else None
        right: Counter[str] = Counter()
        total: Counter[str] = Counter()
        route_right: Counter[str] = Counter()
        route_total: Counter[str] = Counter()
        tokens = 0
        failed = 0
        for case in cases:
            route_total[case["route"]] += 1
            try:
                decision = await decide(case["message"], has_profile=True, llm=llm, jev=jev)
            except AppError as error:  # the provider failed: not a wrong route, so counted apart
                failed += 1
                print(f"FAILED [{error.code}] {case['message']}")
                continue
            total[decision.layer] += 1
            tokens += decision.tokens
            if decision.route == case["route"]:
                right[decision.layer] += 1
                route_right[case["route"]] += 1
            else:
                print(
                    f"WRONG [{decision.layer} {decision.confidence:.2f}] {case['message']}"
                    f"  want {case['route']}, got {decision.route}"
                )
        await llm.aclose()
        if jev is not None:
            await jev.aclose()
        async with sessions() as db:
            calls = await db.execute(
                select(LlmCall.task, LlmCall.outcome, func.count(), func.sum(LlmCall.prompt_tokens))
                .group_by(LlmCall.task, LlmCall.outcome)
                .order_by(LlmCall.task, LlmCall.outcome)
            )
            for task, outcome, count, spent in calls:
                print(f"calls {task} {outcome}: {count}, input tokens {spent}")
        await engine.dispose()
    for layer in sorted(total):
        print(f"{layer}: {right[layer]}/{total[layer]}")
    for route in sorted(route_total):
        print(f"{route}: {route_right[route]}/{route_total[route]}")
    print(f"all: {sum(right.values())}/{len(cases)}, provider failures: {failed}")
    print(f"LLM tokens: {tokens}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    words = sys.argv[1:]
    with_jev = "jev" in words
    names = [word for word in words if word != "jev"]
    asyncio.run(evaluate(names[0] if names else "tuned", use_jev=with_jev))
