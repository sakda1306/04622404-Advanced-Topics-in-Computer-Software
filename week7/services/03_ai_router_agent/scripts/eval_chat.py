"""Run the chat probes against the real LLM (manual; needs GROQ_* or GEMINI_* env).

    cd services/03_ai_router_agent && python scripts/eval_chat.py

Every probe goes through the real router; only the chat reply and the LLM classifier are live,
everything else is the test fixture. The report lists where each probe went, what the checked
reply was (or which template stood in) and writes eval/results/chat.json. Read every `applied`
reply by eye: the validator is the safety net, not a substitute for reading. It exits 1 when a
probe that must be chat is not, a football probe becomes chat, or more than 30% of chat replies
were refused by the validator.
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from app.clients import ServiceClients  # noqa: E402
from app.router import Router  # noqa: E402
from app.teams import TeamDirectory  # noqa: E402
from test_router import FakeClients  # noqa: E402

PROBE_FILE = ROOT / "tests" / "chat_probes.jsonl"
RESULT_FILE = ROOT.parents[1] / "eval" / "results" / "chat.json"
PROBES = [json.loads(line) for line in PROBE_FILE.read_text(encoding="utf-8").splitlines() if line]
MAX_REJECTED_SHARE = 0.3
CONTEXT = {"season": "2026", "current_matchweek": 5, "now": "2026-09-26T10:00:00+07:00"}


def summarize(rows: list[dict]) -> dict:
    chat = [row for row in rows if row["route"] == "chat"]
    llm = [row for row in chat if row["chat"] is not None]
    count = {state: sum(row["chat"] == state for row in llm) for state in ("applied", "rejected", "unavailable")}
    misrouted = sum((row["expect"] == "chat" and row["route"] != "chat")
                    or (row["expect"] == "football" and row["route"] == "chat") for row in rows)
    rejected_share = count["rejected"] / len(llm) if llm else 0.0
    return {"probes": len(rows), "chat_routes": len(chat), **count, "misrouted": misrouted,
            "rejected_share": round(rejected_share, 3), "ok": misrouted == 0 and rejected_share <= MAX_REJECTED_SHARE}


class LiveClients(FakeClients):
    """Fixture services except the chat reply and the LLM classifier, which go to the live LLM."""

    def __init__(self, live):
        super().__init__()
        self.live = live
        self.classifier = {"data": {"label": "general_football", "score": 0.5}}  # below 0.75: the LLM decides

    async def chat(self, system, user, request_id):
        await asyncio.sleep(2)  # stay under the free-tier tokens-per-minute cap
        return await self.live.chat(system, user, request_id)

    async def llm_decide(self, query, request_id):
        await asyncio.sleep(2)
        return await self.live.llm_decide(query, request_id)


async def main() -> int:
    teams = TeamDirectory.from_file(ROOT / "data" / "team_aliases.json")
    clients = LiveClients(ServiceClients(None))
    router = Router(clients, teams)
    rows = []
    for index, probe in enumerate(PROBES):
        result = await router.route({
            "request_id": f"chat-eval-{index}", "session_id": "chat-eval",
            "user": {"id": "chat-eval", "favorite_team_id": probe.get("favorite_team_id"),
                     "language": probe.get("language", "th")},
            "query": probe["query"], "history": probe.get("history", []), "context": CONTEXT})
        row = {"query": probe["query"], "expect": probe["expect"], "route": result["route"],
               "intent": result["trace"]["intent"], "layer": result["trace"]["decided_at_layer"],
               "chat": result["trace"]["chat"], "answer": result["answer"]}
        rows.append(row)
        print(f"[{row['route']:<10}{str(row['chat']):<12}] {row['query']}\n    -> {row['answer']}")
    report = summarize(rows)
    print("\n" + json.dumps(report, ensure_ascii=False, indent=2))
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps({"summary": report, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
