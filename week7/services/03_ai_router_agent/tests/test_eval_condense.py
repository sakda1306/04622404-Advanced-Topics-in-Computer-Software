"""The live condense report must be able to fail: it compares routing, not validate() with itself."""

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eval_condense", ROOT / "scripts" / "eval_condense.py")
eval_condense = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eval_condense)
CASES = {json.loads(line)["id"]: json.loads(line) for line in
         (ROOT / "tests" / "followup_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}


class CannedLive:
    """Plays the LLM: answers each case with its canned rewrite, or an override."""

    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    async def condense(self, query, history, request_id):
        return {"standalone_query": self.overrides.get(request_id, CASES[request_id]["canned_standalone"] or query)}


class EvalCondenseTests(unittest.IsolatedAsyncioTestCase):
    async def test_good_rewrites_beat_the_flag_off(self):
        report = await eval_condense.evaluate(CannedLive())
        self.assertNotIn("invented_rate_after_validate", report)
        self.assertEqual(report["accepted_but_wrong_route"], 0)
        self.assertGreater(report["routing_accuracy_with_condense"], report["routing_accuracy_flag_off"])
        self.assertFalse(report["regressed"])

    async def test_accepted_rewrite_that_routes_wrong_is_counted(self):
        report = await eval_condense.evaluate(CannedLive({"f02": "ใครเป็นโค้ช"}))
        self.assertEqual(report["accepted_but_wrong_route"], 1)
        wrong = [row for row in report["rows"] if row["id"] == "f02"][0]
        self.assertEqual(wrong["status"], "accepted")
        self.assertNotEqual(wrong["with_condense"], wrong["expected"])

    async def test_invented_raw_rate_counts_rejected_inventions(self):
        report = await eval_condense.evaluate(CannedLive())
        self.assertGreater(report["invented_rate_raw"], 0)
