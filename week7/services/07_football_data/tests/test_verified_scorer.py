"""Verified scorer answers use the curated official reference only."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.history import verified_season_top_scorer


class VerifiedScorerTests(unittest.TestCase):
    def test_supported_seasons_have_official_winners(self):
        expected = {
            "2022": ("Erling Haaland", 36),
            "2023": ("Erling Haaland", 27),
            "2024": ("Mohamed Salah", 29),
            "2025": ("Erling Haaland", 27),
        }
        for season, (player, goals) in expected.items():
            with self.subTest(season=season):
                winner = verified_season_top_scorer(season)
                self.assertEqual((winner["player"], winner["goals"]), (player, goals))
                self.assertEqual(winner["season_label"], f"{season}/{(int(season) + 1) % 100:02d}")
                self.assertTrue(winner["source_url"].startswith("https://www.premierleague.com/"))

    def test_unverified_season_is_unavailable(self):
        self.assertIsNone(verified_season_top_scorer("2020"))

    def test_joint_winners_are_unavailable_until_supported(self):
        self.assertIsNone(self._read_record([["Salah", 23], ["Son", 23]]))

    def test_invalid_runner_up_goals_raise_validation_error(self):
        for goals in (None, "22"):
            with (
                self.subTest(goals=goals),
                self.assertRaisesRegex(ValueError, "reference is invalid"),
            ):
                self._read_record([["Salah", 23], ["Son", goals]])

    def _read_record(self, podium):
        record = {
            "2021": {
                "winner_full_name": "Mohamed Salah",
                "top3": podium,
                "url": "https://www.premierleague.com/en/news/example",
            }
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scorer_reference.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with patch("app.history.SCORER_REFERENCE_PATH", path):
                return verified_season_top_scorer("2021")


if __name__ == "__main__":
    unittest.main()
