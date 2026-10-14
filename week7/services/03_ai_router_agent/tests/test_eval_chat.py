import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eval_chat", ROOT / "scripts" / "eval_chat.py")
eval_chat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eval_chat)
PROBES, summarize = eval_chat.PROBES, eval_chat.summarize
PROBE_FILE = ROOT / "tests" / "chat_probes.jsonl"


class EvalChatTests(unittest.TestCase):
    def test_probe_file_is_valid(self):
        probes = [json.loads(line) for line in PROBE_FILE.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(probes, PROBES)
        self.assertGreaterEqual(len(probes), 28)
        for probe in probes:
            self.assertIn(probe["expect"], ("chat", "any", "football"))
            self.assertTrue(probe["query"].strip())

    def test_summary_flags_misrouted_probes_and_a_high_rejection_rate(self):
        rows = [
            {"expect": "chat", "route": "chat", "chat": "applied"},
            {"expect": "chat", "route": "chat", "chat": "rejected"},
            {"expect": "chat", "route": "general_ai", "chat": None},
            {"expect": "football", "route": "chat", "chat": "applied"},
            {"expect": "any", "route": "decline", "chat": None},
        ]
        report = summarize(rows)
        self.assertEqual(report["chat_routes"], 3)
        self.assertEqual(report["applied"], 2)
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(report["unavailable"], 0)
        self.assertEqual(report["misrouted"], 2)
        self.assertFalse(report["ok"])
        good = summarize([{"expect": "chat", "route": "chat", "chat": "applied"}] * 4)
        self.assertTrue(good["ok"])
        self.assertEqual(good["misrouted"], 0)
