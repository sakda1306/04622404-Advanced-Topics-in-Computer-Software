import unittest

from eval_routes import evaluate


class EvalTests(unittest.IsolatedAsyncioTestCase):
    async def test_routing_cases_through_router(self):
        report = await evaluate()
        self.assertEqual(report["total"], 58)
        self.assertEqual(report["correct"], 58, report["failures"])
