import unittest
from pathlib import Path
from unittest.mock import patch

from app.teams import TeamDirectory
from app.translate import fuse, multi_query_enabled, needs_translation, validate_translation


TEAMS = TeamDirectory.from_file(Path(__file__).parents[1] / "data" / "team_aliases.json")


def chunk(chunk_id):
    return {"chunk_id": chunk_id, "text": chunk_id, "source": {"doc_id": chunk_id.split("#")[0]}}


class FlagTests(unittest.TestCase):
    def test_flag_defaults_on(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(multi_query_enabled())

    def test_flag_values(self):
        for value, expected in (("true", True), ("1", True), ("OFF", False), (" no ", False),
                                ("false", False), ("0", False)):
            with patch.dict("os.environ", {"ROUTER_MULTI_QUERY_ENABLED": value}):
                self.assertEqual(multi_query_enabled(), expected, value)

    def test_needs_translation_only_for_thai(self):
        self.assertTrue(needs_translation("ใครยิง"))
        self.assertTrue(needs_translation("Arsenal ชนะไหม"))
        self.assertFalse(needs_translation("Who scored for Arsenal?"))


class ValidateTests(unittest.TestCase):
    def test_validate_accepts_club_names_for_nicknames(self):
        self.assertEqual(validate_translation("เมื่อวานปืนใหญ่ชนะไหม", " Did Arsenal win yesterday? ", TEAMS),
                         "Did Arsenal win yesterday?")

    def test_validate_accepts_time_words(self):
        self.assertIsNotNone(validate_translation("หงส์แดงเมื่อวานยิงกี่ลูก",
                                                  "Liverpool goals yesterday", TEAMS))

    def test_validate_rejects_added_team(self):
        self.assertIsNone(validate_translation("เมื่อวานปืนใหญ่ชนะไหม",
                                               "Arsenal vs Chelsea result yesterday", TEAMS))

    def test_validate_rejects_dropped_team(self):
        self.assertIsNone(validate_translation("ปืนใหญ่ชนะไหม", "Did they win?", TEAMS))
        self.assertIsNone(validate_translation("ปืนใหญ่เจอสิงห์บลูผลเป็นยังไง", "Arsenal result", TEAMS))
        self.assertIsNotNone(validate_translation("ปืนใหญ่เจอสิงห์บลูผลเป็นยังไง",
                                                  "Arsenal vs Chelsea result", TEAMS))

    def test_validate_rejects_added_number(self):
        self.assertIsNone(validate_translation("ทีมไหนแชมป์ยุโรป 88", "European champion 1988", TEAMS))
        self.assertIsNotNone(validate_translation("ใครได้แชมป์บอลโลกปี 1954",
                                                  "FIFA World Cup 1954 winner", TEAMS))

    def test_validate_rejects_empty_long_and_citations(self):
        self.assertIsNone(validate_translation("ใครยิง", "  ", TEAMS))
        self.assertIsNone(validate_translation("ใครยิง", "who scored " * 30, TEAMS))
        self.assertIsNone(validate_translation("ใครยิง", "Salah scored [1]", TEAMS))


class FuseTests(unittest.TestCase):
    def test_fuse_merges_duplicates_and_orders_by_rrf(self):
        fused = fuse([chunk("a#0"), chunk("b#0")], [chunk("c#0"), chunk("a#0")])
        self.assertEqual([c["chunk_id"] for c in fused], ["a#0", "c#0", "b#0"])

    def test_fuse_ties_keep_base_order_first(self):
        fused = fuse([chunk("a#0")], [chunk("b#0")])
        self.assertEqual([c["chunk_id"] for c in fused], ["a#0", "b#0"])

    def test_fuse_with_one_side_empty(self):
        self.assertEqual([c["chunk_id"] for c in fuse([], [chunk("b#0")])], ["b#0"])
        self.assertEqual([c["chunk_id"] for c in fuse([chunk("a#0")], [])], ["a#0"])

    def test_fuse_keeps_chunks_without_id_apart_by_text(self):
        fused = fuse([{"text": "x", "source": {}}], [{"text": "y", "source": {}}])
        self.assertEqual([c["text"] for c in fused], ["x", "y"])
