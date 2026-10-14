import unittest

from app.prediction_text import (match_prediction_text, percent, simulation_focus,
                                 summarize_simulation, thai_datetime)

SNAPSHOT = {
    "season": "2026", "as_of": "2026-09-30T22:50:00+07:00", "stale": False, "n_sims": 10000,
    "teams": [
        {"team_id": 65, "short_name": "Man City", "points": 15, "expected_points": 80.2,
         "p_title": 0.38, "p_top4": 0.9, "p_relegation": 0.0},
        {"team_id": 57, "short_name": "Arsenal", "points": 12, "expected_points": 74.3,
         "p_title": 0.31, "p_top4": 0.82, "p_relegation": 0.0},
        {"team_id": 44, "short_name": "Burnley", "points": 1, "expected_points": 30.1,
         "p_title": 0.0, "p_top4": 0.0, "p_relegation": 0.61},
    ],
}


class PredictionTextTests(unittest.TestCase):
    def test_percent(self):
        self.assertEqual([percent(0.4849), percent(0.004), percent(0)], ["48%", "<1%", "0%"])

    def test_thai_datetime(self):
        self.assertEqual(thai_datetime("2026-09-30T22:50:00+07:00"), "30 ก.ย. 2569 22:50")
        self.assertIsNone(thai_datetime(None))

    def test_focus(self):
        self.assertEqual(simulation_focus("ใครเสี่ยงตกชั้น"), "relegation")
        self.assertEqual(simulation_focus("ใครจะติดท็อป 4"), "top4")
        self.assertEqual(simulation_focus("ใครจะได้แชมป์"), "title")
        self.assertEqual(simulation_focus("ทำนายฤดูกาลนี้"), "title")

    def test_match_text_has_disclaimer_and_date(self):
        text = match_prediction_text({"content": "Arsenal ชนะ 48%",
                                      "data": {"as_of": "2026-09-30T22:50:00+07:00"}})
        self.assertTrue(text.startswith("Arsenal ชนะ 48%"))
        self.assertIn("ข้อมูล ณ 30 ก.ย. 2569 22:50", text)
        self.assertIn("ไม่ใช่คำแนะนำการพนัน", text)

    def test_single_team_row(self):
        text = summarize_simulation(SNAPSHOT, "title", [57])
        self.assertIn("Arsenal", text)
        self.assertIn("แต้มที่คาดเมื่อจบฤดูกาล 74", text)
        self.assertIn("แชมป์ 31%", text)
        self.assertIn("จำลอง 10,000 ครั้ง", text)

    def test_league_title_list(self):
        text = summarize_simulation(SNAPSHOT, "title", [])
        self.assertLess(text.index("Man City"), text.index("Arsenal"))

    def test_relegation_list_and_stale_note(self):
        text = summarize_simulation({**SNAPSHOT, "stale": True}, "relegation", [])
        self.assertTrue(text.splitlines()[1].startswith("1. Burnley 61%"))
        self.assertIn("ผลนี้อาจยังไม่อัปเดตล่าสุด", text)

    def test_unknown_team(self):
        self.assertIn("ไม่พบทีมนี้", summarize_simulation(SNAPSHOT, "title", [999]))

    def test_several_named_teams_each_get_a_row(self):
        text = summarize_simulation(SNAPSHOT, "title", [57, 65])
        self.assertIn("Arsenal: แต้มตอนนี้ 12", text)
        self.assertIn("Man City: แต้มตอนนี้ 15", text)
