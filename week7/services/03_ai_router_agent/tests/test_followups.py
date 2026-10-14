"""Multi-turn follow-up cases with canned condense replies (spec 2026-10-01 §6.4)."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.router import Router
from app.teams import TeamDirectory
from test_router import FakeClients


ROOT = Path(__file__).resolve().parents[1]
CASES = [json.loads(line) for line in
         (ROOT / "tests" / "followup_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
SOURCE = {"ref": 1, "doc_id": "followup-1", "title": "Sample", "category": "match_report",
          "origin": "football-data.org", "season": "2026", "matchweek": 5, "team_ids": [],
          "fetched_at": "2026-09-26T09:00:00+07:00", "url": None}


class FollowupCaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.dict("os.environ", {"ROUTER_CONDENSE_ENABLED": "true"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.teams = TeamDirectory.from_file(ROOT / "data" / "team_aliases.json")

    def test_case_count(self):
        self.assertEqual(len(CASES), 14)

    async def test_followup_cases(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                clients = FakeClients()
                clients.chunks = [{"text": "sample", "source": SOURCE}]
                clients.standalone = case["canned_standalone"]
                result = await Router(clients, self.teams).route({
                    "request_id": case["id"], "session_id": "session-1",
                    "user": {"id": "user-1", "favorite_team_id": None, "language": "th"},
                    "query": case["query"], "history": case["history"],
                    "context": {"season": "2026", "current_matchweek": 5,
                                "now": "2026-09-26T10:00:00+07:00"}})
                self.assertEqual(result["route"], case["route"])
                self.assertEqual(result["trace"]["intent"], case["intent"])
                self.assertEqual(result["trace"]["condense"], case["condense"])
                if "team_ids" in case:
                    self.assertEqual(result["trace"]["filters"].get("team_ids"), case["team_ids"])
                for name, payload, _ in clients.calls:
                    if name in ("generate", "general"):
                        # The user's own question, never the rewrite; a team note may follow it.
                        self.assertEqual(payload["query"].splitlines()[0], case["query"])
