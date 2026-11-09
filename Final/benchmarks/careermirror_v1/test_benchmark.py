"""Metric checks: missing predictions must not inflate benchmark results."""

import tempfile
import unittest
from pathlib import Path

from benchmark import fingerprint, score, validate


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = validate()

    def test_fingerprint_ignores_line_endings_but_not_content(self):
        with tempfile.TemporaryDirectory() as folder:
            lf, crlf, edited = (Path(folder) / name for name in ("lf", "crlf", "edited"))
            lf.write_bytes(b"one\ntwo\n")
            crlf.write_bytes(b"one\r\ntwo\r\n")
            edited.write_bytes(b"one\ntwo!\n")
            self.assertEqual(fingerprint(lf), fingerprint(crlf))
            self.assertNotEqual(fingerprint(lf), fingerprint(edited))

    def test_missing_outputs_fail_and_answers_stay_ungraded(self):
        result = score(self.cases, [])
        self.assertEqual(result["retrieval"]["hit_at_3"], 0)
        self.assertEqual(result["routing"]["accuracy"], 0)
        self.assertIsNone(result["answer_review"]["pass_rate_on_graded"])

    def test_perfect_retrieval_and_routing_do_not_grade_answers(self):
        predictions = [
            {
                "id": c["id"],
                "retrieved_chunk_ids": c["expected"],
                "route": c["expected_route"] or "unused",
            }
            for c in self.cases
        ]
        result = score(self.cases, predictions)
        self.assertEqual(result["retrieval"]["mrr_at_3"], 1)
        self.assertEqual(result["routing"]["accuracy"], 1)
        self.assertEqual(result["answer_review"]["coverage"], 0)

    def test_rank_and_alternative_labels(self):
        case = next(c for c in self.cases if len(c["expected"]) > 1)
        result = score(
            self.cases,
            [
                {
                    "id": case["id"],
                    "retrieved_chunk_ids": ["unrelated", case["expected"][1]],
                }
            ],
        )
        self.assertAlmostEqual(result["retrieval"]["mrr_at_3"], 0.5 / 80)
        self.assertEqual(result["retrieval"]["hit_at_1"], 0)
        self.assertEqual(result["retrieval"]["hit_at_3"], 1 / 80)

    def test_bad_prediction_ids_and_duplicate_chunks_rejected(self):
        for rows in [
            [{"id": "unknown"}],
            [{"id": "CMG-001"}] * 2,
            [{"id": "CMG-001", "retrieved_chunk_ids": ["x", "x"]}],
        ]:
            with self.assertRaises(ValueError):
                score(self.cases, rows)

    def test_rubric_requires_answer_and_reviewer(self):
        row = {"id": "CMG-001", "criteria_pass": {"C1": True}}
        with self.assertRaises(ValueError):
            score(self.cases, [row])
        row.update(answer="Example answer", reviewer="reviewer-1")
        result = score(self.cases, [row])
        self.assertEqual(result["answer_review"]["criteria_graded"], 1)
        self.assertEqual(result["answer_review"]["pass_rate_on_graded"], 1)
        self.assertLess(result["answer_review"]["coverage"], 0.01)


if __name__ == "__main__":
    unittest.main()
