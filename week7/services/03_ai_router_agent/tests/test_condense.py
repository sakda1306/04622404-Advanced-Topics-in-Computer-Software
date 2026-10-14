import unittest
from pathlib import Path
from unittest.mock import patch

from app.condense import condense_enabled, invented_entities, needs_condense, validate
from app.teams import TeamDirectory


TEAMS = TeamDirectory.from_file(Path(__file__).parents[1] / "data" / "team_aliases.json")
LIVERPOOL_TURN = [{"role": "user", "content": "ลิเวอร์พูลชนะไหมเมื่อวาน"},
                  {"role": "assistant", "content": "ลิเวอร์พูลชนะ 2-1 [1]"}]


class FlagTests(unittest.TestCase):
    def test_flag_defaults_on(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(condense_enabled())

    def test_flag_values(self):
        for value, expected in (("true", True), ("1", True), ("yes", True), ("false", False),
                                ("0", False), ("no", False), ("OFF", False), (" False ", False)):
            with patch.dict("os.environ", {"ROUTER_CONDENSE_ENABLED": value}):
                self.assertEqual(condense_enabled(), expected, value)


class GateTests(unittest.TestCase):
    def gate(self, query, history=LIVERPOOL_TURN):
        return needs_condense(query, history, TEAMS, "2026")

    def test_no_history_never_condenses(self):
        for query in ("แล้วใครยิง", "who scored?", "มีนักเตะคนไหนบ้าง"):
            self.assertFalse(self.gate(query, []), query)

    def test_assistant_only_history_never_condenses(self):
        self.assertFalse(self.gate("แล้วใครยิง", [{"role": "assistant", "content": "สวัสดีครับ"}]))

    def test_follow_up_markers_condense(self):
        for query in ("แล้วใครยิง", "เขายิงกี่ลูก", "นัดก่อนหน้านั้นล่ะ", "แล้วเชลซีล่ะ",
                      "ทีมนี้นัดต่อไปเตะกับใคร", "what about the next match?",
                      "and who scored for them"):
            self.assertTrue(self.gate(query), query)

    def test_short_question_condenses(self):
        self.assertTrue(self.gate("ใครเป็นโค้ช"))
        self.assertTrue(self.gate("ใครทำประตู"))

    def test_team_bound_intent_without_team_condenses(self):
        self.assertTrue(self.gate("มีนักเตะคนไหนบ้าง"))

    def test_standalone_questions_skip(self):
        for query in ("อาร์เซนอลอยู่อันดับเท่าไหร่", "ตารางคะแนนพรีเมียร์ลีก",
                      "ใครได้บัลลงดอร์ปี 2008", "กฎล้ำหน้าคืออะไร",
                      "Who won Arsenal vs Chelsea yesterday?"):
            self.assertFalse(self.gate(query), query)


class ValidateTests(unittest.TestCase):
    def check(self, rewritten, original="แล้วใครยิง", history=LIVERPOOL_TURN):
        return validate(original, rewritten, history, TEAMS)

    def test_accepts_rewrite_using_history_team(self):
        self.assertEqual(self.check("  ใครยิงประตูให้ลิเวอร์พูลในนัดเมื่อวาน "),
                         "ใครยิงประตูให้ลิเวอร์พูลในนัดเมื่อวาน")

    def test_accepts_team_alias_from_history(self):
        self.assertEqual(self.check("ใครยิงประตูให้หงส์แดงเมื่อวาน"), "ใครยิงประตูให้หงส์แดงเมื่อวาน")

    def test_accepts_number_from_history(self):
        self.assertIsNotNone(self.check("ใครยิงประตูให้ลิเวอร์พูลในนัดที่ชนะ 2-1"))

    def test_rejects_new_team(self):
        self.assertIsNone(self.check("ใครยิงประตูให้ลิเวอร์พูลและเชลซีเมื่อวาน"))

    def test_rejects_new_number(self):
        self.assertIsNone(self.check("ใครยิงประตูให้ลิเวอร์พูลนัดที่ 7"))

    def test_rejects_answer_with_citation(self):
        self.assertIsNone(self.check("ซาลาห์ยิงให้ลิเวอร์พูล [1]"))

    def test_rejects_statement_when_user_asked(self):
        self.assertIsNone(self.check("ลิเวอร์พูลชนะเมื่อวาน"))

    def test_rejects_empty_and_too_long(self):
        self.assertIsNone(self.check("   "))
        self.assertIsNone(self.check("ใครยิงประตูให้ลิเวอร์พูล " * 20))

    def test_english_rewrite(self):
        history = [{"role": "user", "content": "Who won Arsenal vs Chelsea yesterday?"},
                   {"role": "assistant", "content": "Arsenal won 1-0 [1]"}]
        self.assertEqual(validate("who scored?", "Who scored in Arsenal vs Chelsea yesterday?", history, TEAMS),
                         "Who scored in Arsenal vs Chelsea yesterday?")

    def test_invented_entities_lists_new_teams_and_numbers(self):
        self.assertEqual(invented_entities("แล้วใครยิง", "เชลซีกับลิเวอร์พูลนัดที่ 7 ใครยิง",
                                           LIVERPOOL_TURN, TEAMS), ["Chelsea", "7"])
        self.assertEqual(invented_entities("แล้วใครยิง", "ใครยิงให้ลิเวอร์พูล", LIVERPOOL_TURN, TEAMS), [])


class ReviewFixValidateTests(unittest.TestCase):
    ARSENAL_TURN = [{"role": "user", "content": "อาร์เซนอลอยู่อันดับเท่าไหร่"},
                    {"role": "assistant", "content": "อาร์เซนอลอยู่อันดับ 2 [1]"}]
    SCORER_TURN = [{"role": "user", "content": "ใครยิงประตูมากที่สุด"},
                   {"role": "assistant", "content": "ฮาลันด์ [1]"}]

    def test_rejects_rewrite_that_drops_the_users_team(self):
        self.assertIsNone(validate("แล้วเชลซีล่ะ", "อยู่อันดับเท่าไหร่", self.ARSENAL_TURN, TEAMS))
        self.assertIsNone(validate("แล้วเชลซีล่ะ", "อาร์เซนอลอยู่อันดับเท่าไหร่", self.ARSENAL_TURN, TEAMS))

    def test_rejects_added_time_scope(self):
        self.assertIsNone(validate("แล้วใครยิงเยอะสุดล่ะ", "ฤดูกาลที่แล้วใครยิงประตูมากที่สุด",
                                   self.SCORER_TURN, TEAMS))
        self.assertIsNone(validate("and the top scorer?", "Who was the top scorer last season?",
                                   self.SCORER_TURN, TEAMS))
        self.assertIsNone(validate("แล้วเชลซีล่ะ", "เชลซีเมื่อวานอยู่อันดับเท่าไหร่", self.ARSENAL_TURN, TEAMS))

    def test_keeps_time_scope_already_in_the_chat(self):
        self.assertIsNotNone(validate("แล้วใครยิง", "ใครยิงประตูให้ลิเวอร์พูลเมื่อวาน", LIVERPOOL_TURN, TEAMS))

    def test_invented_entities_lists_added_time_scope(self):
        self.assertEqual(invented_entities("แล้วใครยิงเยอะสุดล่ะ", "ฤดูกาลที่แล้วใครยิงประตูมากที่สุด",
                                           self.SCORER_TURN, TEAMS), ["ฤดูกาลที่แล้ว"])


class MinorFixTests(unittest.TestCase):
    def test_english_standalone_question_with_team_skips(self):
        for query in ("Who won between Arsenal and Chelsea yesterday?", "Is that Arsenal's best season ever?"):
            self.assertFalse(needs_condense(query, LIVERPOOL_TURN, TEAMS, "2026"), query)

    def test_english_follow_up_openers_condense(self):
        for query in ("what about Spurs?", "And Chelsea, who scored for them?", "how about the next match?"):
            self.assertTrue(needs_condense(query, LIVERPOOL_TURN, TEAMS, "2026"), query)

    def test_english_pronoun_without_team_condenses(self):
        self.assertTrue(needs_condense("Did they win the previous match too?", LIVERPOOL_TURN, TEAMS, "2026"))

    def test_rejects_added_number_words(self):
        self.assertIsNone(validate("แล้วใครยิง", "ใครยิงให้ลิเวอร์พูลนัดที่เจ็ด", LIVERPOOL_TURN, TEAMS))
        self.assertIsNone(validate("and who scored?", "Who scored for Liverpool in matchweek seven?",
                                   LIVERPOOL_TURN, TEAMS))

    def test_keeps_number_words_from_the_chat(self):
        history = [{"role": "user", "content": "ลิเวอร์พูลชนะสองประตูใช่ไหม"},
                   {"role": "assistant", "content": "ใช่ [1]"}]
        self.assertIsNotNone(validate("แล้วใครยิง", "ใครยิงสองประตูให้ลิเวอร์พูล", history, TEAMS))
        self.assertEqual(invented_entities("แล้วใครยิง", "ใครยิงให้ลิเวอร์พูลนัดที่เจ็ด", LIVERPOOL_TURN, TEAMS),
                         ["เจ็ด"])

    def test_short_alias_inside_another_word_is_not_a_known_team(self):
        history = [{"role": "user", "content": "ลิเวอร์พูลชนะไหมเมื่อวาน"},
                   {"role": "assistant", "content": "ลิเวอร์พูลชนะ แฟนบอลแต่งชุดผีเสื้อ [1]"}]
        self.assertIsNone(validate("แล้วใครยิง", "ใครยิงให้ลิเวอร์พูลกับแมนยูเมื่อวาน", history, TEAMS))

    def test_long_alias_in_the_chat_is_a_known_team(self):
        history = [{"role": "user", "content": "ผีแดงชนะไหมเมื่อวาน"}, {"role": "assistant", "content": "ชนะ [1]"}]
        self.assertIsNotNone(validate("แล้วใครยิง", "ใครยิงให้แมนยูเมื่อวาน", history, TEAMS))

    def test_none_content_is_not_a_user_turn(self):
        self.assertFalse(needs_condense("แล้วใครยิง", [{"role": "user", "content": None}], TEAMS, "2026"))
        self.assertEqual(invented_entities("แล้วใครยิง", "ใครยิง None", [{"role": "user", "content": None}],
                                           TEAMS), [])


class RulesResolvedTests(unittest.TestCase):
    def decision(self, intent, team_ids, route="football_rag", layer="rules"):
        from app.decisions import Decision
        decision = Decision(route, intent, layer, 0.9, "test")
        decision.team_ids = team_ids
        return decision

    def test_team_bound_intent_with_team_is_resolved(self):
        from app.condense import rules_resolved
        for intent in ("match_result", "fixture_schedule", "standings_stats", "player_info"):
            self.assertTrue(rules_resolved(self.decision(intent, [64])), intent)

    def test_unresolved_decisions(self):
        from app.condense import rules_resolved
        self.assertFalse(rules_resolved(None))
        self.assertFalse(rules_resolved(self.decision("player_info", [])))
        self.assertFalse(rules_resolved(self.decision("trivia_history", [64])))
        self.assertFalse(rules_resolved(self.decision("prediction", [57], route="clarify")))
        self.assertFalse(rules_resolved(self.decision("match_result", [64], layer="classifier")))


class LanguageTests(unittest.TestCase):
    def test_rejects_english_rewrite_of_thai_question(self):
        self.assertIsNone(validate("แล้วใครยิง", "Who scored for Liverpool in the 2-1 win?", LIVERPOOL_TURN, TEAMS))

    def test_rejects_thai_rewrite_of_english_question(self):
        history = [{"role": "user", "content": "Who won Arsenal vs Chelsea?"}, {"role": "assistant", "content": "Arsenal [1]"}]
        self.assertIsNone(validate("who scored?", "ใครยิงประตูให้อาร์เซนอล", history, TEAMS))

    def test_mixed_team_name_keeps_thai_rewrite(self):
        self.assertIsNotNone(validate("แล้วใครยิง", "ใครยิงประตูให้ Liverpool เมื่อวาน", LIVERPOOL_TURN, TEAMS))
