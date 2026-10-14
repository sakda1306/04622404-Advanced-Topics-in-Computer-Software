"""Run the follow-up cases against the real condense LLM (manual; needs GROQ_* or GEMINI_* env).

    cd services/03_ai_router_agent && python scripts/eval_condense.py

Each case goes through the real router twice, once with the live rewrite and once with the
flag off. The report shows how often the raw LLM rewrite invented a team, number or time
scope (validate() rejects those), and whether accepted rewrites route correctly. It exits 1
when routing with condense is less accurate than with the flag off.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app.clients import ServiceClients  # noqa: E402
from app.condense import invented_entities  # noqa: E402
from app.router import Router  # noqa: E402
from app.teams import TeamDirectory  # noqa: E402
from test_router import FakeClients  # noqa: E402


CONTEXT = {"season": "2026", "current_matchweek": 5, "now": "2026-09-26T10:00:00+07:00"}
SOURCE = {"ref": 1, "doc_id": "eval-1", "title": "Sample", "category": "match_report",
          "origin": "football-data.org", "season": "2026", "matchweek": 5, "team_ids": [],
          "fetched_at": None, "url": None}
STATUS = {"applied": "accepted", "unchanged": "accepted", "rejected": "rejected",
          "unavailable": "unavailable", None: "skipped"}


class LiveCondenseClients(FakeClients):
    """Fixture services for everything except condense, which goes to the live LLM."""

    def __init__(self, live):
        super().__init__()
        self.chunks = [{"text": "sample", "source": SOURCE}]
        self.live = live
        self.raw = None

    async def condense(self, query, history, request_id):
        self.calls.append(("condense", query, request_id))
        reply = await self.live.condense(query, history, request_id)
        self.raw = str(reply.get("standalone_query") or "")
        return reply


def outcome(case, result):
    picked = [result["route"], result["trace"]["intent"]]
    if "team_ids" in case:
        picked.append(result["trace"]["filters"].get("team_ids"))
    return picked


async def run(teams, case, live, enabled):
    clients = LiveCondenseClients(live)
    with patch.dict(os.environ, {"ROUTER_CONDENSE_ENABLED": "true" if enabled else "false"}):
        result = await Router(clients, teams).route({
            "request_id": case["id"], "session_id": "eval",
            "user": {"id": "eval", "favorite_team_id": None, "language": "th"},
            "query": case["query"], "history": case["history"], "context": CONTEXT})
    return result, clients.raw


def rate(count, total):
    return round(count / total, 3) if total else None


async def evaluate(live, cases=None):
    teams = TeamDirectory.from_file(ROOT / "data" / "team_aliases.json")
    if cases is None:
        cases = [json.loads(line) for line in
                 (ROOT / "tests" / "followup_cases.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    rows = []
    for case in cases:
        with_condense, raw = await run(teams, case, live, True)
        flag_off, _ = await run(teams, case, live, False)
        row = {"id": case["id"], "query": case["query"], "status": STATUS[with_condense["trace"]["condense"]],
               "rewritten": raw, "with_condense": outcome(case, with_condense), "flag_off": outcome(case, flag_off)}
        if raw is not None:
            row["invented_raw"] = invented_entities(case["query"], raw, case["history"], teams)
        if case["condense"] == "applied":
            row["expected"] = outcome(case, {"route": case["route"], "trace": {
                "intent": case["intent"], "filters": {"team_ids": case.get("team_ids")}}})
        rows.append(row)

    called = [row for row in rows if "invented_raw" in row]
    scored = [row for row in rows if "expected" in row]
    with_accuracy = rate(sum(row["with_condense"] == row["expected"] for row in scored), len(scored))
    off_accuracy = rate(sum(row["flag_off"] == row["expected"] for row in scored), len(scored))
    return {
        "cases": len(rows),
        "llm_called": len(called),
        "rejected_rate": rate(sum(row["status"] == "rejected" for row in called), len(called)),
        "invented_rate_raw": rate(sum(bool(row["invented_raw"]) for row in called), len(called)),
        "accepted_but_wrong_route": sum(row["status"] == "accepted" and row["with_condense"] != row["expected"]
                                        for row in scored),
        "routing_accuracy_with_condense": with_accuracy,
        "routing_accuracy_flag_off": off_accuracy,
        "regressed": with_accuracy is not None and off_accuracy is not None and with_accuracy < off_accuracy,
        "rows": rows,
    }


async def main():
    report = await evaluate(ServiceClients(None))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["regressed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
