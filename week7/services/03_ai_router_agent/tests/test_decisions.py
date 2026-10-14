import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.decisions import (INTENT_MAP, classify_intent, decide, from_intent, historical_scorer_season,
                           history_filters, prediction_kind, resolve_clarify_reply, team_clarify,
                           title_year_clarify)
from app.teams import TeamDirectory


CASES = Path(__file__).with_name("routing_cases.jsonl")
CHAT_CASES = Path(__file__).with_name("chat_cases.jsonl")
TEAMS = TeamDirectory.from_file(Path(__file__).parents[1] / "data" / "team_aliases.json")
CONTEXT = {"season": "2026", "current_matchweek": 5, "now": "2026-09-26T10:00:00+07:00"}


class DecisionTests(unittest.TestCase):
    def test_title_year_clarify_texts(self):
        self.assertEqual(title_year_clarify(2025, True), (
            "หมายถึงแชมป์พรีเมียร์ลีกฤดูกาล 2024/25 (จบปี 2025) หรือ 2025/26 (เริ่มปี 2025) ครับ",
            "Do you mean the Premier League 2024/25 season (ended in 2025) or 2025/26 (began in 2025)?"))
        self.assertEqual(title_year_clarify(2025, False), (
            "หมายถึงแชมป์รายการไหนครับ ถ้าเป็นพรีเมียร์ลีก ปี 2025 ตรงกับฤดูกาล 2024/25 (จบปี 2025) "
            "หรือ 2025/26 (เริ่มปี 2025)",
            "Which competition do you mean? For the Premier League, 2025 covers 2024/25 (ended in 2025) "
            "and 2025/26 (began in 2025)."))
        thai, english = title_year_clarify(1990, False)
        self.assertIn("ถ้าเป็นลีกสูงสุดอังกฤษ ปี 1990 ตรงกับฤดูกาล 1989/90 (จบปี 1990) หรือ 1990/91", thai)
        self.assertNotIn("พรีเมียร์ลีก", thai)
        self.assertIn("For the English top-flight, 1990 covers 1989/90", english)
        self.assertIn("1999/00 (จบปี 2000) หรือ 2000/01 (เริ่มปี 2000)", title_year_clarify(2000, True)[0])

    def test_team_clarify_text(self):
        self.assertEqual(team_clarify(), (
            'หมายถึงแชมป์ของทีมไหนครับ เช่น "แมนยูได้แชมป์พรีเมียร์ลีกกี่สมัย"',
            'Which club do you mean? For example: "How many Premier League titles have Manchester United won?"'))

    # Live chat test 2026-10-04: all-time finishes and points were answered from this season's table.
    def test_all_time_table_questions_use_the_archive(self):
        cases = {
            "แมนยูจบอันดับแย่ที่สุดในพรีเมียร์ลีกอันดับเท่าไหร่": "Man United Premier League record best finish",
            "นิวคาสเซิลจบอันดับดีที่สุดในพรีเมียร์ลีกอันดับเท่าไหร่": "Newcastle Premier League record best finish",
            "อาร์เซนอลเก็บแต้มรวมในพรีเมียร์ลีกทั้งหมดกี่แต้ม": "Arsenal Premier League record best finish",
            "ลิเวอร์พูลเคยจบอันดับแย่ที่สุดในพรีเมียร์ลีกอันดับเท่าไหร่": "Liverpool Premier League record",
            "ทีมไหนเก็บแต้มรวมในพรีเมียร์ลีกมากที่สุดตลอดกาล": "Premier League all-time records most points",
            "What is Arsenal's best ever Premier League finish?": "What is Arsenal's best ever",
        }
        for query, rewrite in cases.items():
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual((decision.route, decision.intent), ("football_rag", "trivia_history"))
                self.assertEqual(decision.filters, {"category": ["historical"]})
                self.assertTrue(decision.rewritten_query.startswith(rewrite), decision.rewritten_query)

    def test_current_table_questions_stay_standings(self):
        for query in ("อาร์เซนอลอยู่อันดับเท่าไหร่", "อาร์เซนอลได้กี่แต้มแล้ว", "ตอนนี้ใครเป็นจ่าฝูง",
                      "อันดับ 1 ตอนนี้คือใคร", "ตารางคะแนนนัดที่ 5",
                      "อาร์เซนอลเคยอยู่อันดับ 1 ฤดูกาลนี้ไหม", "How many points do Arsenal have this season?"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).intent, "standings_stats")
        # "แต้มรวม" alone usually means this season's table; the rules leave it to the classifier.
        decision = decide("อาร์เซนอลมีแต้มรวมเท่าไหร่", CONTEXT, [], TEAMS)
        self.assertNotEqual(decision.filters if decision else None, {"category": ["historical"]})

    # Live chat test 2026-10-05: "แชมป์ปี 2025" and "ได้แชมป์กี่สมัย" found nothing; the user wants a question back.
    def test_ambiguous_title_year_asks_back(self):
        decision = decide("แชมป์พรีเมียร์ลีกปี 2025 คือทีมไหน", CONTEXT, [], TEAMS)
        self.assertEqual((decision.route, decision.layer), ("clarify", "guard"))
        self.assertEqual(decision.clarify_text, title_year_clarify(2025, True)[0])
        decision = decide("แชมป์ปี 2025 คือทีมไหน", CONTEXT, [], TEAMS)
        self.assertEqual(decision.clarify_text, title_year_clarify(2025, False)[0])
        self.assertEqual(decide("Who were the champions in 2025?", CONTEXT, [], TEAMS).route, "clarify")

    def test_explicit_seasons_and_named_teams_are_not_clarified(self):
        for query in ("แชมป์พรีเมียร์ลีกฤดูกาล 2024/25 คือทีมไหน", "อาร์เซนอลได้แชมป์ปี 2004 ไหม",
                      "ใครได้แชมป์พรีเมียร์ลีกฤดูกาล 2004/05", "ฤดูกาลที่แล้วใครได้แชมป์พรีเมียร์ลีก"):
            with self.subTest(query=query):
                self.assertNotEqual(decide(query, CONTEXT, [], TEAMS).route, "clarify")

    def test_other_competitions_and_former_clubs_are_not_clarified(self):
        for query in ("ใครได้แชมป์บอลโลกปี 2022", "บราซิลได้แชมป์บอลโลกกี่สมัย", "แบล็คเบิร์นได้แชมป์กี่สมัย",
                      "ใครได้แชมป์ดิวิชั่น 1 อังกฤษปี 1990", "คอนเฟดคัพปี 2003 ใครได้แชมป์"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.route if decision else None, "clarify")

    def test_predictions_are_not_clarified(self):
        self.assertEqual(decide("ใครจะได้แชมป์ปี 2027", CONTEXT, [], TEAMS).intent, "prediction")

    def test_title_count_without_a_team_asks_which_club(self):
        decision = decide("ได้แชมป์กี่สมัย", CONTEXT, [], TEAMS)
        self.assertEqual((decision.route, decision.clarify_text), ("clarify", team_clarify()[0]))
        for query in ("ทีมไหนได้แชมป์มากที่สุด", "มีกี่ทีมที่เคยได้แชมป์พรีเมียร์ลีก", "แมนยูได้แชมป์กี่สมัย"):
            with self.subTest(query=query):
                self.assertNotEqual(decide(query, CONTEXT, [], TEAMS).route, "clarify")
        history = [{"role": "user", "content": "แมนยูเป็นยังไงบ้าง"}]
        self.assertNotEqual(decide("ได้แชมป์กี่สมัย", CONTEXT, history, TEAMS).route, "clarify")

    def test_explicit_season_title_search_names_champions(self):
        decision = decide("แชมป์พรีเมียร์ลีกฤดูกาล 2024/25 คือทีมไหน", CONTEXT, [], TEAMS)
        self.assertIn("champions final table", decision.rewritten_query)
        self.assertNotIn("final table standings", decision.rewritten_query)

    def test_range_questions_search_the_archive_without_a_season(self):
        decision = decide("ตั้งแต่ปี 2010 แมนซิตี้ได้แชมป์พรีเมียร์ลีกกี่สมัย", CONTEXT, [], TEAMS)
        self.assertEqual((decision.intent, decision.filters), ("trivia_history", {"category": ["historical"]}))
        self.assertTrue(decision.rewritten_query.startswith("Man City Premier League titles seasons"))
        self.assertEqual(decide("How many titles have Man City won since 2010?", CONTEXT, [], TEAMS).filters,
                         {"category": ["historical"]})

    def test_english_title_and_relegation_questions_use_rules(self):
        for query in ("How many Premier League titles have Manchester United won?",
                      "Which club has won the most Premier League titles?",
                      "How many times have Newcastle been relegated?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual((decision.layer, decision.intent), ("rules", "trivia_history"))
        decision = decide("Which club has won the most Premier League titles?", CONTEXT, [], TEAMS)
        self.assertEqual(decision.rewritten_query, "Which club has won the most Premier League titles?")

    # Live chat test 2026-10-05 (c39): as asked, other clubs' "all eras" chunks outranked the club's record.
    def test_english_club_record_questions_name_the_club(self):
        cases = {
            "How many Premier League titles have Manchester United won?":
                "Manchester United FC Premier League record titles How many",
            "How many times have Newcastle been relegated?": "Newcastle United FC Premier League record relegated How",
            "Have Tottenham ever won the Premier League?": "Tottenham Hotspur FC Premier League record titles Have",
        }
        for query, rewrite in cases.items():
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual((decision.layer, decision.filters), ("rules", {"category": ["historical"]}))
                self.assertTrue(decision.rewritten_query.startswith(rewrite), decision.rewritten_query)
        # A season named keeps the season search.
        decision = decide("Did Arsenal win the Premier League title in 2004/05?", CONTEXT, [], TEAMS)
        self.assertNotEqual(decision.reasoning if decision else None, "English club record question")

    @staticmethod
    def clarify_history(question, answer):
        return [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]

    def test_a_short_reply_after_a_clarify_is_merged(self):
        year_any = self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0])
        merged = resolve_clarify_reply("2024/25", year_any)
        self.assertEqual(merged, "แชมป์ปี 2025 คือทีมไหน 2024/25 พรีเมียร์ลีก")
        self.assertEqual(decide(merged, CONTEXT, year_any, TEAMS).filters,
                         {"category": ["historical"], "season": "2024"})
        team = self.clarify_history("ได้แชมป์กี่สมัย", team_clarify()[0])
        self.assertEqual(resolve_clarify_reply("แมนยู", team, TEAMS), "ได้แชมป์กี่สมัย แมนยู")
        self.assertEqual(decide("ได้แชมป์กี่สมัย แมนยู", CONTEXT, team, TEAMS).team_ids, [66])
        named = resolve_clarify_reply("พรีเมียร์ลีก", year_any)
        self.assertEqual(decide(named, CONTEXT, year_any, TEAMS).clarify_text, title_year_clarify(2025, True)[0])

    def test_a_new_question_after_a_clarify_is_not_merged(self):
        year_any = self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0])
        for reply in ("ใครได้แชมป์บอลโลกปี 2022", "แมนยูได้แชมป์กี่สมัย", "x" * 41, ""):
            with self.subTest(reply=reply):
                self.assertIsNone(resolve_clarify_reply(reply, year_any))
        other = self.clarify_history("ยูไนเต็ดชนะไหม", "หมายถึงทีมใดหรือแมตช์ไหนครับ")
        self.assertIsNone(resolve_clarify_reply("2024/25", other))
        self.assertIsNone(resolve_clarify_reply("2024/25", []))

    # Final review 2026-10-05: inputs just outside the spec's literal examples.
    def test_new_questions_after_a_clarify_are_not_merged(self):
        year_any = self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0])
        team = self.clarify_history("ได้แชมป์กี่สมัย", team_clarify()[0])
        for reply in ("อาร์เซนอลนัดต่อไป", "ข่าวล่าสุดของแมนยู", "ลิเวอร์พูลเจอเชลซีนัดหน้า", "อาร์เซนอลแต้มล่าสุด",
                      "Arsenal fixtures", "ผลบอลเมื่อวาน", "ตารางคะแนนล่าสุด", "โปรแกรมแข่งพรุ่งนี้", "สวัสดี",
                      "ขอบคุณครับ", "ลีกสูงสุด"):
            for history in (year_any, team):
                with self.subTest(reply=reply, asked=history[0]["content"]):
                    self.assertIsNone(resolve_clarify_reply(reply, history, TEAMS))
        self.assertEqual(resolve_clarify_reply("2024/25", year_any, TEAMS),
                         "แชมป์ปี 2025 คือทีมไหน 2024/25 พรีเมียร์ลีก")
        named = self.clarify_history("แชมป์พรีเมียร์ลีกปี 2025 คือทีมไหน", title_year_clarify(2025, True)[0])
        self.assertIsNone(resolve_clarify_reply("พรีเมียร์ลีก", named, TEAMS))
        self.assertEqual(resolve_clarify_reply("2024/25", named, TEAMS), "แชมป์พรีเมียร์ลีกปี 2025 คือทีมไหน 2024/25")

    def test_current_table_superlatives_stay_off_the_archive(self):
        for query in ("อาร์เซนอลอยู่อันดับเท่าไหร่ในลีกสูงสุด", "ทีมในลีกสูงสุดอังกฤษอันดับ 1 คือใคร",
                      "ทีมไหนอยู่อันดับต่ำสุด", "ทีมไหนเคยได้อันดับ 1", "ใครยิงประตูสูงสุดอันดับ 1",
                      "ดาวซัลโวสูงสุดอันดับ 1 คือใคร", "Who has the lowest points?", "How many total points do Arsenal have?",
                      "What is Arsenal's total points?", "Who has the best points tally?",
                      "Who has the highest points total in the league?", "อาร์เซนอลมีแต้มทั้งหมดกี่แต้ม",
                      "ทีมไหนมีแต้มสูงสุด", "ทีมไหนแต้มต่ำสุด", "ใครมีแต้มสูงสุดในลีก"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.reasoning if decision else None, "คำถามสถิติทั้งยุค")

    def test_predictions_and_betting_with_all_time_words_keep_their_intent(self):
        self.assertEqual(decide("ราคาบอลทีมไหนจะจบอันดับดีที่สุดในพรีเมียร์ลีก", CONTEXT, [], TEAMS).route, "decline")
        for query in ("อาร์เซนอลจะจบอันดับดีที่สุดในพรีเมียร์ลีกเท่าไหร่", "ทำนายว่าลิเวอร์พูลจะจบอันดับสูงสุดในพรีเมียร์ลีกที่เท่าไหร่",
                      "อาร์เซนอลมีโอกาสจบอันดับดีที่สุดในพรีเมียร์ลีกเท่าไหร่"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).intent, "prediction")
        for query in ("Will Arsenal finish in the best Premier League position ever?",
                      "Where will Arsenal finish at best in the Premier League?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.reasoning if decision else None, "คำถามสถิติทั้งยุค")

    def test_named_players_nations_and_competitions_are_not_clarified(self):
        for query in ("อาร์เจนตินาได้แชมป์โลกกี่สมัย", "อาร์เจนตินาได้แชมป์กี่สมัย", "เรอัลมาดริดได้แชมป์กี่สมัย",
                      "เมสซี่ได้แชมป์กี่ครั้ง", "How many titles has Messi won?", "คริสเตียโน โรนัลโด้ ได้แชมป์ UCL กี่สมัย",
                      "แชมป์ UCL ปี 2023", "ucl winners 2020", "แชมป์ซีรีอาปี 2020", "แชมป์ฝรั่งเศสปี 2020",
                      "บาร์เซโลน่าได้แชมป์ปี 2015 ไหม", "ซาลาห์ได้แชมป์ปี 2020 ไหม", "Who won the Golden Boot in 2018?",
                      "Who won the PFA award in 2020?", "Who won the treble in 1999?", "แชมป์ดาวซัลโวปี 2018"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.route if decision else None, "clarify")

    def test_future_title_years_are_not_clarified(self):
        for query in ("แชมป์ปี 2027 จะเป็นใคร", "ใครมีลุ้นแชมป์ปี 2027", "Who will be champions in 2027?",
                      "Who will be the champion in 2027?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.route if decision else None, "clarify")

    def test_current_relegation_and_runner_up_questions_are_not_history(self):
        for query in ("Who is in the relegation zone?", "Which teams are in the relegation zone?",
                      "Who are the relegation candidates this season?", "Is Arsenal runner-up this season?",
                      "Who is runner-up in the table?", "Who got relegated yesterday?", "What is the relegation rule?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.intent if decision else None, "trivia_history")

    def test_current_season_and_non_title_ranges(self):
        for query in ("ตั้งแต่ปี 2026 อาร์เซนอลได้กี่แต้ม", "อาร์เซนอลได้กี่แต้มตั้งแต่เดือนกันยายน 2026"):
            with self.subTest(query=query):
                self.assertNotEqual(decide(query, CONTEXT, [], TEAMS).reasoning, "คำถามช่วงเวลา")
        decision = decide("ตั้งแต่ปี 2010 ใครได้ดาวซัลโวบ่อยสุด", CONTEXT, [], TEAMS)
        self.assertNotEqual(decision.reasoning if decision else None, "คำถามช่วงเวลา")
        decision = decide("ตั้งแต่ปี 2010 แมนยูจบอันดับดีที่สุดอันดับเท่าไหร่", CONTEXT, [], TEAMS)
        self.assertTrue(decision.rewritten_query.startswith("Man United Premier League record best finish"),
                        decision.rewritten_query)

    # Live chat test 2026-10-05 (c27, c37, c38, c63): each club's record summary is searched on its own.
    def test_club_record_questions_search_each_club(self):
        city = [{"role": "user", "content": "แมนซิตี้ได้แชมป์พรีเมียร์ลีกกี่สมัย"},
                {"role": "assistant", "content": "แมนเชสเตอร์ ซิตี้ได้แชมป์พรีเมียร์ลีก 8 สมัย"}]

        def record_ids(query, history=()):
            decision = decide(query, CONTEXT, list(history), TEAMS)
            return decision.record_team_ids if decision else []

        cases = [
            ("แมนยูกับลิเวอร์พูลใครได้แชมป์พรีเมียร์ลีกมากกว่ากัน", [], [66, 64]),
            ("เชลซีกับอาร์เซนอลใครได้แชมป์พรีเมียร์ลีกเยอะกว่า", [], [61, 57]),
            ("แล้วเคยตกชั้นไหม", city, [65]),
            ("แมนยูจบอันดับแย่ที่สุดในพรีเมียร์ลีกอันดับเท่าไหร่", [], [66]),
            ("How many Premier League titles have Manchester United won?", [], [66]),
            ("Who has more Premier League titles, Chelsea or Arsenal?", [], [61, 57]),
        ]
        for query, history, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(record_ids(query, history), expected)
        for query in ("อาร์เซนอลเคยชนะเชลซีกี่ครั้ง", "อาร์เซนอลได้แชมป์ฤดูกาล 2003/04 ไหม",
                      "แมนยูได้แชมป์เอฟเอคัพกี่สมัย", "ใครยิงให้ลิเวอร์พูลมากที่สุด", "อาร์เซนอลอยู่อันดับเท่าไหร่",
                      "ทีมไหนได้แชมป์พรีเมียร์ลีกมากที่สุด"):
            with self.subTest(query=query):
                self.assertEqual(record_ids(query), [])
        self.assertEqual(record_ids("แล้วตอนนี้อยู่อันดับเท่าไหร่", city), [])

    # Live chat test 2026-10-05: "แล้วจบอันดับดีที่สุดเท่าไหร่" after a Newcastle question read this season's table.
    def test_a_best_or_worst_finish_is_all_time_without_the_league_named(self):
        newcastle = [{"role": "user", "content": "นิวคาสเซิลได้แชมป์พรีเมียร์ลีกกี่สมัย"},
                     {"role": "assistant", "content": "นิวคาสเซิล ยูไนเต็ดยังไม่เคยได้แชมป์พรีเมียร์ลีก"}]
        decision = decide("แล้วจบอันดับดีที่สุดเท่าไหร่", CONTEXT, newcastle, TEAMS)
        self.assertEqual((decision.intent, decision.filters, decision.record_team_ids),
                         ("trivia_history", {"category": ["historical"]}, [67]))
        for query in ("อาร์เซนอลจบอันดับแย่ที่สุดอันดับเท่าไหร่", "What is Liverpool's worst finish?"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).reasoning, "คำถามสถิติทั้งยุค")
        # Final review 2026-10-05: Europe, the Championship, a cup group, this match or week are not the PL record.
        for query in ("อาร์เซนอลจบอันดับดีที่สุดฤดูกาลนี้ได้ไหม", "บาร์เซโลน่าจบอันดับดีที่สุดในลาลีกาอันดับเท่าไหร่",
                      "อาร์เซนอลจะจบอันดับดีที่สุดเท่าไหร่", "ลิเวอร์พูลจบอันดับดีที่สุดในยุโรปเท่าไหร่",
                      "What is Liverpool's best finish in the Championship?", "อาร์เซนอลจบอันดับแย่ที่สุดในกลุ่ม",
                      "Arsenal's worst group stage finish", "อาร์เซนอลจบอันดับดีที่สุดสัปดาห์นี้",
                      "ใครจบอันดับดีที่สุดในนัดนี้", "Who finished best this week?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.reasoning if decision else None, "คำถามสถิติทั้งยุค")

    # Coach questions (CONTRACT v1.16): the head coach document, not the squad list, should lead.
    def test_coach_questions_search_the_head_coach_document(self):
        spurs = [{"role": "user", "content": "สเปอร์สได้แชมป์กี่สมัย"}, {"role": "assistant", "content": "ยังไม่เคย"}]
        cases = [
            ("ตอนนี้ใครทำหน้าที่เป็นโค้ชของ Man United", [], "Manchester United FC head coach manager 2026/27 "),
            ("โค้ชลิเวอร์พูลคือใคร", [], "Liverpool FC head coach manager 2026/27 "),
            ("ใครเป็นผู้จัดการทีมอาร์เซนอล", [], "Arsenal FC head coach manager 2026/27 "),
            ("กุนซือแมนซิตี้ชื่ออะไร", [], "Manchester City FC head coach manager 2026/27 "),
            ("แล้วโค้ชล่ะ", spurs, "Tottenham Hotspur FC head coach manager 2026/27 "),
            ("Who is the Chelsea manager?", [], "Chelsea FC head coach manager 2026/27 "),
            ("Who coaches Arsenal?", [], "Arsenal FC head coach manager 2026/27 "),
        ]
        for query, history, start in cases:
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, history, TEAMS)
                self.assertEqual(decision.intent, "player_info")
                self.assertTrue(decision.rewritten_query.startswith(start), decision.rewritten_query)
        for query in ("Who won Manager of the Month?", "Who is Arsenal's general manager?",
                      "ใครเป็นโค้ชที่อยู่นานที่สุด", "Who is Arsenal's assistant coach?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                rewrite = decision.rewritten_query if decision else ""
                self.assertNotIn("head coach manager", rewrite or "")

    # Final review 2026-10-05: the coach documents hold the current coach only.
    def test_past_coach_and_goal_questions_do_not_search_the_current_coach(self):
        for query in ("Who was Man United manager in 1999?",
                      "Who was the Arsenal manager when they won the Invincibles season?",
                      "How many goals has Arsenal scored since the new manager arrived?",
                      "ใครเคยเป็นโค้ชแมนยู", "อดีตกุนซือลิเวอร์พูลคือใคร", "โค้ชแมนยูปี 2008 คือใคร"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotIn("head coach manager", (decision.rewritten_query or "") if decision else "")

    # Review minors 2026-10-05.
    def test_pl_means_the_premier_league_as_a_whole_word(self):
        self.assertEqual(decide("Who won the PL in 2016?", CONTEXT, [], TEAMS).clarify_text,
                         title_year_clarify(2016, True)[0])
        decision = decide("Who are Arsenal's players?", CONTEXT, [], TEAMS)
        self.assertEqual(decision.intent, "player_info")

    def test_a_season_reply_before_1992_names_the_top_flight(self):
        asked = self.clarify_history("แชมป์ปี 1990 คือทีมไหน", title_year_clarify(1990, False)[0])
        self.assertEqual(resolve_clarify_reply("1989/90", asked, TEAMS), "แชมป์ปี 1990 คือทีมไหน 1989/90 ลีกสูงสุดอังกฤษ")

    def test_person_and_women_title_questions_do_not_search_club_records(self):
        for query in ("ซาลาห์ได้แชมป์กับลิเวอร์พูลกี่สมัย", "เป๊ปได้แชมป์กับแมนซิตี้กี่สมัย",
                      "How many titles has Arteta won with Arsenal?", "Arsenal women titles",
                      "ทีมหญิงอาร์เซนอลได้แชมป์กี่สมัย"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(decision.record_team_ids if decision else [], [])
        self.assertEqual(decide("เชลซีกับอาร์เซนอลใครได้แชมป์พรีเมียร์ลีกเยอะกว่า", CONTEXT, [], TEAMS).record_team_ids,
                         [61, 57])

    # Final review 2026-10-05: Thai has no spaces, so "แชมป์…กับ" also spans a two-club comparison.
    def test_two_club_comparisons_keep_the_club_record_search(self):
        cases = {"ใครได้แชมป์มากกว่ากันระหว่างเชลซีกับอาร์เซนอล": [61, 57],
                 "อาร์เซนอลได้แชมป์กี่สมัยเทียบกับเชลซี": [57, 61],
                 "แชมป์พรีเมียร์ลีกเชลซีกับอาร์เซนอลใครเยอะกว่า": [61, 57],
                 "How many Premier League titles have Chelsea won compared with Arsenal?": [61, 57]}
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).record_team_ids, expected)

    def test_other_staff_do_not_get_the_head_coach_search(self):
        for query in ("Who is Arsenal's goalkeeper coach?", "Who is the Arsenal kit manager?",
                      "โค้ชผู้รักษาประตูของอาร์เซนอลคือใคร"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotIn("head coach manager", (decision.rewritten_query or "") if decision else "")

    def test_an_unknown_club_finish_is_not_a_premier_league_record(self):
        decision = decide("บุรีรัมย์จบอันดับดีที่สุดเท่าไหร่", CONTEXT, [], TEAMS)
        self.assertNotEqual(decision.reasoning if decision else None, "คำถามสถิติทั้งยุค")
        self.assertEqual(decide("อาร์เซนอลจบอันดับแย่ที่สุดอันดับเท่าไหร่", CONTEXT, [], TEAMS).reasoning,
                         "คำถามสถิติทั้งยุค")

    def test_a_relegation_range_searches_the_relegation_record(self):
        decision = decide("ตั้งแต่ปี 2000 ทีมไหนตกชั้นบ่อยสุด", CONTEXT, [], TEAMS)
        self.assertEqual(decision.filters, {"category": ["historical"]})
        self.assertTrue(decision.rewritten_query.startswith("Premier League relegations most relegated clubs"))

    def test_war_years_are_not_asked_back(self):
        for query, war in (("ใครได้แชมป์ลีกอังกฤษปี 1942", "Second World War"),
                           ("แชมป์ปี 1917 คือทีมไหน", "First World War")):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual((decision.route, decision.filters), ("football_rag", {"category": ["historical"]}))
                self.assertIn(war, decision.rewritten_query)
        for query in ("แชมป์ปี 1939 คือทีมไหน", "แชมป์ปี 1946 คือทีมไหน"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).route, "clarify")

    # Natural short replies and repeated questions back (2026-10-05).
    def year_asks(self):
        return {
            "any": self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0]),
            "league": self.clarify_history("แชมป์พรีเมียร์ลีกปี 2025 คือทีมไหน", title_year_clarify(2025, True)[0]),
            "english": self.clarify_history("Who were the champions in 2025?", title_year_clarify(2025, False)[1]),
        }

    def test_natural_replies_pick_the_offered_season(self):
        for reply, season in (("จบปี 2025", "2024"), ("ฤดูกาลที่จบปี 2025", "2024"), ("อันแรก", "2024"),
                              ("first", "2024"), ("2024/25?", "2024"), ("24/25 ครับ", "2024"),
                              ("เริ่มปี 2025", "2025"), ("อันหลัง", "2025"), ("second", "2025")):
            for name, history in self.year_asks().items():
                with self.subTest(reply=reply, asked=name):
                    merged = resolve_clarify_reply(reply, history, TEAMS)
                    self.assertIsNotNone(merged)
                    self.assertEqual(decide(merged, CONTEXT, history, TEAMS).filters,
                                     {"category": ["historical"], "season": season})

    def test_both_seasons_search_the_champions_by_year(self):
        for reply in ("ทั้งสองฤดูกาล", "both"):
            for name, history in self.year_asks().items():
                with self.subTest(reply=reply, asked=name):
                    decision = decide(resolve_clarify_reply(reply, history, TEAMS), CONTEXT, history, TEAMS)
                    self.assertEqual(decision.filters, {"category": ["historical"]})
                    self.assertIn("champions by year 2025", decision.rewritten_query)
        decision = decide("Premier League champions by year 2025", CONTEXT, [], TEAMS)
        self.assertEqual(decision.filters, {"category": ["historical"]})

    def test_replies_that_do_not_answer_are_not_merged(self):
        asks = self.year_asks()
        for reply in ("จบปี 2023", "หลังปี 2010", "หลังจากนั้นล่ะ"):
            with self.subTest(reply=reply):
                self.assertIsNone(resolve_clarify_reply(reply, asks["any"], TEAMS))
        team = self.clarify_history("ได้แชมป์กี่สมัย", team_clarify()[0])
        self.assertIsNone(resolve_clarify_reply("อันแรก", team, TEAMS))

    def test_a_second_question_back_keeps_the_first_question(self):
        first = title_year_clarify(2025, False)[0]
        history = [{"role": "user", "content": "แชมป์ปี 2025 คือทีมไหน"}, {"role": "assistant", "content": first},
                   {"role": "user", "content": "พรีเมียร์ลีก"},
                   {"role": "assistant", "content": title_year_clarify(2025, True)[0]}]
        self.assertEqual(resolve_clarify_reply("2024/25", history, TEAMS),
                         "แชมป์ปี 2025 คือทีมไหน พรีเมียร์ลีก 2024/25")
        broken = [{"role": "user", "content": "แชมป์ปี 2025 คือทีมไหน"}, {"role": "assistant", "content": "สวัสดีครับ"},
                  {"role": "user", "content": "อันแรก"}, {"role": "assistant", "content": first}]
        self.assertEqual(resolve_clarify_reply("2024/25", broken, TEAMS), "อันแรก 2024/25 พรีเมียร์ลีก")
        deep = [{"role": "user", "content": "แชมป์ปี 2025 คือทีมไหน"}]
        for _ in range(4):
            deep += [{"role": "assistant", "content": first}, {"role": "user", "content": "พรีเมียร์ลีก"}]
        deep.append({"role": "assistant", "content": first})
        self.assertFalse(resolve_clarify_reply("2024/25", deep, TEAMS).startswith("แชมป์ปี 2025"))

    # Minors left in PR #64 (2026-10-05).
    # Final review 2026-10-05 (clarify replies).
    def test_a_new_question_in_the_chain_starts_a_new_chain(self):
        year = title_year_clarify(2025, False)[0]
        history = [{"role": "user", "content": "แชมป์ปี 2025 คือทีมไหน"}, {"role": "assistant", "content": year},
                   {"role": "user", "content": "ได้แชมป์กี่สมัย"}, {"role": "assistant", "content": team_clarify()[0]}]
        self.assertEqual(resolve_clarify_reply("อาร์เซนอล", history, TEAMS), "ได้แชมป์กี่สมัย อาร์เซนอล")
        history = [{"role": "user", "content": "ได้แชมป์กี่สมัย"}, {"role": "assistant", "content": team_clarify()[0]},
                   {"role": "user", "content": "แชมป์ปี 2016 คือทีมไหน"},
                   {"role": "assistant", "content": title_year_clarify(2016, False)[0]}]
        self.assertEqual(resolve_clarify_reply("อันแรก", history, TEAMS), "แชมป์ปี 2016 คือทีมไหน 2015/16 พรีเมียร์ลีก")

    def test_ordinary_follow_up_words_keep_the_all_time_route(self):
        newcastle = [{"role": "user", "content": "นิวคาสเซิลได้แชมป์พรีเมียร์ลีกกี่สมัย"}, {"role": "assistant", "content": "0"}]
        for query in ("จบอันดับดีที่สุดคืออันดับอะไร", "แล้วจบอันดับดีที่สุดปีไหน", "แล้วจบอันดับดีที่สุดอันดับไหน",
                      "แล้วจบอันดับดีที่สุดเท่าไหร่หรอ", "แล้วทีมนี้จบอันดับดีที่สุดเท่าไหร่",
                      "แล้วเขาจบอันดับดีที่สุดเท่าไหร่", "what's their best finish?", "and their best finish so far?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, newcastle, TEAMS)
                self.assertEqual(decision.reasoning if decision else None, "คำถามสถิติทั้งยุค")

    def test_a_competition_reply_with_the_asked_year_is_merged(self):
        asked = self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0])
        for reply in ("FA Cup 2025", "เอฟเอคัพปี 2025", "พรีเมียร์ลีกปี 2025"):
            with self.subTest(reply=reply):
                self.assertEqual(resolve_clarify_reply(reply, asked, TEAMS), f"แชมป์ปี 2025 คือทีมไหน {reply}")

    def test_championships_are_titles_not_the_second_tier(self):
        decision = decide("Which club has won the most league championships since 1992?", CONTEXT, [], TEAMS)
        self.assertEqual(decision.filters if decision else None, {"category": ["historical"]})

    # Minors left in PR #65 (2026-10-06).
    def test_champions_by_year_stays_with_league_years(self):
        for query in ("FA Cup champions by year", "champions by year 2027", "champions by year since 2000"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.reasoning if decision else None, "แชมป์ตามปี")
        asked = self.clarify_history("แชมป์ปี 1990 คือทีมไหน", title_year_clarify(1990, False)[0])
        decision = decide(resolve_clarify_reply("ทั้งสองฤดูกาล", asked, TEAMS), CONTEXT, asked, TEAMS)
        self.assertTrue(decision.rewritten_query.startswith("English top-flight First Division champions"),
                        decision.rewritten_query)

    # Review of the PR #65 minors fix (2026-10-06).
    def test_natural_replies_with_fillers_still_merge(self):
        asked = self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0])
        english = self.clarify_history("Who were the champions in 2025?", title_year_clarify(2025, False)[1])
        for reply, history, expected in (("ที่จบปี 2025", asked, "2024/25"), ("อันที่จบปี 2025", asked, "2024/25"),
                                         ("the one that ended in 2025", english, "2024/25"),
                                         ("season that began in 2025", english, "2025/26"),
                                         ("both of them", english, "champions by year 2025"),
                                         ("เอาทั้งคู่", asked, "champions by year 2025"),
                                         ("ทั้งสองฤดูกาลเลยครับ", asked, "champions by year 2025")):
            with self.subTest(reply=reply):
                self.assertIn(expected, resolve_clarify_reply(reply, history, TEAMS) or "")

    def test_the_champions_by_year_prefix_follows_the_year(self):
        cases = (("แชมป์พรีเมียร์ลีกปี 1990 คือทีมไหน", 1990, True, "English top-flight First Division champions"),
                 ("Who won the English top-flight in 2010?", 2010, True, "Premier League"),
                 ("แชมป์ปี 1992 คือทีมไหน", 1992, False, "English top-flight First Division champions Premier League"))
        for question, year, named, prefix in cases:
            with self.subTest(question=question):
                asked = self.clarify_history(question, title_year_clarify(year, named)[0])
                decision = decide(resolve_clarify_reply("ทั้งสองฤดูกาล", asked, TEAMS), CONTEXT, asked, TEAMS)
                self.assertTrue(decision.rewritten_query.startswith(prefix + " "), decision.rewritten_query)

    def test_war_years_in_other_leagues_are_not_the_top_flight(self):
        for query in ("อาร์เซนอลได้แชมป์ลีกวันปี 1942 ไหม", "Did Arsenal win the Championship in 1942?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual(decision.reasoning if decision else None, "ปีที่ไม่มีลีกช่วงสงคราม")

    def test_at_a_ground_is_still_the_clubs_own_record(self):
        self.assertEqual(decide("How many titles have Arsenal won at the Emirates?", CONTEXT, [], TEAMS)
                         .record_team_ids, [57])
        self.assertEqual(decide("How many titles did Salah win at Liverpool?", CONTEXT, [], TEAMS)
                         .record_team_ids, [])

    def test_reply_edges(self):
        asked = self.clarify_history("แชมป์ปี 2025 คือทีมไหน", title_year_clarify(2025, False)[0])
        for reply in ("ทั้งสองทีม", "ก่อนจบปี 2025"):
            with self.subTest(reply=reply):
                self.assertIsNone(resolve_clarify_reply(reply, asked, TEAMS))
        year = title_year_clarify(2025, True)[0]
        again = [{"role": "user", "content": "แชมป์พรีเมียร์ลีกปี 2025 คือทีมไหน"}, {"role": "assistant", "content": year},
                 {"role": "user", "content": "2024/25"}, {"role": "assistant", "content": year}]
        merged = resolve_clarify_reply("อันหลัง", again, TEAMS)
        self.assertEqual(decide(merged, CONTEXT, again, TEAMS).filters.get("season"), "2025")
        empty = [{"role": "user", "content": ""}, {"role": "assistant", "content": year}]
        self.assertIsNone(resolve_clarify_reply("2024/25", empty, TEAMS))

    def test_pr64_minors(self):
        arsenal = [{"role": "user", "content": "อาร์เซนอลได้แชมป์กี่สมัย"}, {"role": "assistant", "content": "4 สมัย"}]
        decision = decide("แล้วบุรีรัมย์จบอันดับดีที่สุดเท่าไหร่", CONTEXT, arsenal, TEAMS)
        self.assertNotEqual(decision.reasoning if decision else None, "คำถามสถิติทั้งยุค")
        self.assertEqual(decide("แล้วจบอันดับดีที่สุดเท่าไหร่", CONTEXT, arsenal, TEAMS).reasoning, "คำถามสถิติทั้งยุค")
        decision = decide("อาร์เซนอลได้แชมป์ปี 1942 ไหม", CONTEXT, [], TEAMS)
        self.assertEqual(decision.filters, {"category": ["historical"]})
        self.assertIn("Second World War", decision.rewritten_query)
        self.assertTrue(decision.rewritten_query.startswith("Arsenal FC "))
        decision = decide("ตั้งแต่ปี 2000 ทีมไหนตกชั้นบ่อยสุดในแชมเปียนชิพ", CONTEXT, [], TEAMS)
        self.assertNotIn("relegations most relegated", (decision.rewritten_query or "") if decision else "")
        english = self.clarify_history("Who were the champions in 1990?", title_year_clarify(1990, False)[1])
        self.assertTrue(resolve_clarify_reply("1989/90", english, TEAMS).endswith(" English top-flight"))
        self.assertEqual(decide("แชมป์plปี 2016 คือทีมไหน", CONTEXT, [], TEAMS).clarify_text,
                         title_year_clarify(2016, True)[0])
        decision = decide("plus size kit Arsenal", CONTEXT, [], TEAMS)
        self.assertNotEqual(decision.route if decision else None, "clarify")
        for query in ("ซาลาห์ได้แชมป์ พรีเมียร์ลีก กับลิเวอร์พูลกี่สมัย", "ซาลาห์อยู่กับลิเวอร์พูลได้แชมป์กี่สมัย",
                      "How many titles did Salah win at Liverpool?"):
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(decision.record_team_ids if decision else [], [])

    def test_season_specific_table_questions_keep_their_season(self):
        decision = decide("อาร์เซนอลจบอันดับเท่าไหร่ในฤดูกาล 2015/16", CONTEXT, [], TEAMS)
        self.assertEqual(decision.filters.get("season"), "2015")

    def test_season_questions_are_prediction_intent(self):
        for query in ("ใครจะได้แชมป์พรีเมียร์ลีกปีนี้", "อาร์เซนอลมีโอกาสติดท็อป 4 กี่เปอร์เซ็นต์",
                      "ใครเสี่ยงตกชั้นมากที่สุด", "ทีมไหนจะตกชั้น", "Who will be relegated this season?",
                      "What are Arsenal's chances of winning the title?"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).intent, "prediction")

    def test_history_questions_stay_trivia(self):
        for query in ("อาร์เซนอลได้แชมป์พรีเมียร์ลีกกี่ครั้ง", "ลิเวอร์พูลได้แชมป์ครั้งล่าสุดเมื่อไร",
                      "เชลซีเคยได้แชมป์พรีเมียร์ลีกกี่ครั้ง"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).intent, "trivia_history")

    def test_prediction_kind(self):
        cases = (
            ("ลิเวอร์พูลกับซิตี้ใครจะชนะ", [64, 65], "match"),
            ("อาร์เซนอลกับลิเวอร์พูล ใครจะได้แชมป์", [57, 64], "season"),
            ("Arsenal, City or Liverpool, who will win the title?", [57, 65, 64], "season"),
            ("ใครจะได้แชมป์ปีนี้", [], "season"),
            ("อาร์เซนอลมีโอกาสติดท็อป 4 กี่ %", [57], "season"),
            ("ใครเสี่ยงตกชั้น", [], "season"),
            ("อาร์เซนอลมีโอกาสชนะไหม", [57], "needs_team"),
            ("ทำนายผลหน่อย", [], "needs_team"),
        )
        for query, team_ids, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(prediction_kind(query, team_ids), expected)

    def test_historical_scorer_year_forms(self):
        cases = (
            ("ลีคปี 2025 ใครยิงเยอะสุด", ("2025", True)),
            ("พรีเมียร์ลีกฤดูกาล 2025/26 ดาวซัลโว", ("2025", False)),
            ("2025-2026 Premier League top scorer", ("2025", False)),
            ("พรีเมียร์ลีก 25/26 ใครทำประตูมากที่สุด", ("2025", False)),
            ("ใครยิงเยอะสุดตอนนี้", None),
            ("ใครยิงประตูมากที่สุดตลอดกาลปี 2025", None),
            ("Who was the top scorer last season", ("2025", False)),
            ("ใครเป็นดาวซัลโวซีซั่นที่แล้ว", ("2025", False)),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(historical_scorer_season(query, "2026"), expected)

    def test_explicit_current_season_scorer_uses_live_standings(self):
        result = decide("พรีเมียร์ลีกฤดูกาล 2026/27 ดาวซัลโว", CONTEXT, [], TEAMS)
        self.assertEqual(result.intent, "standings_stats")
        self.assertEqual(result.filters["season"], "2026")
        self.assertIn("top scorer", result.rewritten_query)

    def test_scorer_review_edge_cases(self):
        cases = (
            ("ดาวซัลโว Everton ตอนนี้", "standings_stats"),
            ("ดาวซัลโวฤดูกาล 2026", "standings_stats"),
            ("ดาวซัลโวฤดูกาล 2026/2027", "standings_stats"),
            ("ดาวซัลโวซีซั่น 2025/26", "trivia_history"),
            ("ผู้รักษาประตูคนไหนเซฟมากที่สุด", "player_info"),
            ("ทีมไหนเสียประตูมากที่สุด", None),
            ("Who was the top scorer last season", "trivia_history"),
            ("ใครเป็นดาวซัลโวซีซั่นที่แล้ว", "trivia_history"),
            ("ดาวซัลโวปีที่แล้ว", "trivia_history"),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                decision = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(decision.intent if decision else None, expected)

    def test_routing_cases(self):
        cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(cases), 58)
        self.assertEqual({route: sum(case["route"] == route for case in cases)
                          for route in {case["route"] for case in cases}},
                         {"football_rag": 20, "general_ai": 8, "local_ai": 11,
                          "clarify": 11, "decline": 8})
        for case in cases:
            with self.subTest(query=case["query"]):
                result = decide(case["query"], CONTEXT, [], TEAMS)
                self.assertIsNotNone(result)
                self.assertEqual(result.route, case["route"])
                if "intent" in case:
                    self.assertEqual(result.intent, case["intent"])

    def test_classifier_threshold_and_mapping(self):
        self.assertEqual(classify_intent("match_result", 0.75).route, "football_rag")
        self.assertIsNone(classify_intent("fixture_schedule", 0.74))
        self.assertEqual(classify_intent("prediction", 0.9).route, "local_ai")
        self.assertIsNone(classify_intent("unknown", 0.99))

    def test_yesterday_date_filter(self):
        result = decide("เมื่อวานปืนใหญ่ชนะไหม", CONTEXT, [], TEAMS)
        self.assertEqual(result.filters["category"], ["match_report"])
        self.assertEqual(result.filters["team_ids"], [57])
        self.assertEqual(result.filters["date_from"], "2026-09-25")
        self.assertEqual(result.filters["date_to"], "2026-09-25")
        self.assertNotIn("matchweek", result.filters)
        self.assertIn("Arsenal", result.rewritten_query)
        self.assertIn("เมื่อวานปืนใหญ่ชนะไหม", result.rewritten_query)

    def test_rewrite_keeps_person_and_question_condition(self):
        query = "ใครยิงประตูชัยให้ลิเวอร์พูลในนัดชิงปี 2005"
        result = decide(query, CONTEXT, [], TEAMS)
        self.assertEqual(result.intent, "trivia_history")
        self.assertIn(query, result.rewritten_query)

    def test_followup_reuses_recent_team(self):
        history = [{"role": "user", "content": "อาร์เซนอลนัดล่าสุดชนะไหม"},
                   {"role": "assistant", "content": "อาร์เซนอลชนะ"}]
        result = decide("แล้วนัดก่อนหน้าล่ะ", CONTEXT, history, TEAMS)
        self.assertEqual(result.route, "football_rag")
        self.assertEqual(result.filters["team_ids"], [57])
        self.assertIn("Arsenal", result.rewritten_query)

    def test_vague_followup_uses_latest_classifiable_user_intent(self):
        history = [{"role": "user", "content": "ทำนายผล แมนซิตี้ กับ ลิเวอร์พูล"},
                   {"role": "assistant", "content": "ยังไม่พร้อม"},
                   {"role": "user", "content": "อาร์เซนอลอยู่อันดับเท่าไร"}]
        result = decide("แล้วล่ะ", CONTEXT, history, TEAMS)
        self.assertEqual(result.intent, "standings_stats")
        self.assertEqual(result.route, "football_rag")

    def test_match_discipline_questions_remain_factual(self):
        for query in ("เมื่อวานลิเวอร์พูลได้ลูกโทษไหม", "ใครโดนใบแดงนัดล่าสุด"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(result.intent, "match_result")
                self.assertEqual(result.filters["category"], ["match_report"])

    def test_discipline_rule_question_stays_general(self):
        result = decide("กฎใบแดงคืออะไร", CONTEXT, [], TEAMS)
        self.assertEqual(result.intent, "general_football")

    def test_title_history_when_is_trivia(self):
        result = decide("ลิเวอร์พูลได้แชมป์ครั้งล่าสุดเมื่อไร", CONTEXT, [], TEAMS)
        self.assertEqual(result.intent, "trivia_history")
        self.assertEqual(result.filters["category"], ["trivia", "historical"])
        self.assertNotIn("season", result.filters)

    def test_team_trivia_does_not_filter_unlabeled_trivia_documents(self):
        result = decide("อาร์เซนอลได้แชมป์พรีเมียร์ลีกกี่ครั้ง", CONTEXT, [], TEAMS)
        self.assertEqual(result.team_ids, [57])
        self.assertEqual(result.filters, {"category": ["trivia", "historical"]})

    def test_full_manchester_club_names_are_recognized(self):
        for name, team_id in (("Manchester United", 66), ("Manchester City", 65)):
            with self.subTest(name=name):
                result = decide(f"{name} นัดล่าสุดชนะไหม", CONTEXT, [], TEAMS)
                self.assertEqual(result.team_ids, [team_id])
                self.assertEqual(result.intent, "match_result")

    def test_other_city_club_is_not_man_city(self):
        result = decide("เลสเตอร์ ซิตี้ ได้แชมป์ปีไหน", CONTEXT, [], TEAMS)
        self.assertNotIn(65, result.team_ids if result else [])

    def test_out_of_range_matchweek_is_clarified(self):
        for query in ("นัดที่ 45 ผลแข่งปืนใหญ่", "matchweek 0 Arsenal result"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(result.route, "clarify")

    def test_english_top_scorer_uses_standings(self):
        result = decide("who is the top scorer", CONTEXT, [], TEAMS)
        self.assertEqual(result.intent, "standings_stats")
        self.assertEqual(result.filters["category"], ["standings"])

    def test_weekly_summary_uses_spaced_matchweek(self):
        result = decide("สรุปพรีเมียร์ลีกนัดที่ 3", CONTEXT, [], TEAMS)
        self.assertEqual(result.intent, "weekly_summary")
        self.assertEqual(result.filters["matchweek"], 3)

    def test_current_scorer_filters_current_matchweek(self):
        result = decide("ใครนำดาวซัลโวตอนนี้", CONTEXT, [], TEAMS)
        self.assertEqual(result.filters["matchweek"], 5)

    def test_current_top_scorer_phrases_use_standings(self):
        for query in (
            "ใครยิงเยอะสุดในลีกตอนนี้",
            "ครยิงเยอะสุดในลีกตอนนี้",
            "ใครทำประตูมากที่สุดในพรีเมียร์ลีกฤดูกาลนี้",
            "ใครทำประตูเยอะที่สุด",
            "ใครยิงเยอะที่สุดตอนนี้",
            "นักเตะคนไหนยิงประตูมากที่สุดฤดูกาลนี้",
            "Who has the most goals this season",
        ):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(result.intent, "standings_stats")
                self.assertEqual(result.filters["category"], ["standings"])
                self.assertEqual(result.filters["matchweek"], 5)
                if query != "Who has the most goals this season":
                    self.assertIn("top scorer", result.rewritten_query)

    def test_historical_scorer_does_not_use_current_standings(self):
        for query in ("ใครยิงมากที่สุดในลีกปี 2020", "ใครยิงประตูมากที่สุดตลอดกาลของพรีเมียร์ลีก"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(result.intent, "trivia_history")

    def test_ambiguous_united(self):
        self.assertEqual(decide("ยูไนเต็ดนัดล่าสุดชนะไหม", CONTEXT, [], TEAMS).route, "clarify")

    def test_alias_does_not_match_inside_english_word(self):
        self.assertEqual(TEAMS.find("Arsenalization"), [])

    def test_prediction_teams_follow_question_order(self):
        result = decide("ทำนายผล แมนซิตี้ กับ ลิเวอร์พูล", CONTEXT, [], TEAMS)
        self.assertEqual(result.team_ids, [65, 64])

    def test_liverpool_duck_alias_resolves_offline(self):
        self.assertEqual(TEAMS.find("เป็ดแดงเตะวันไหน")[0].team_id, 64)
        self.assertIn("Liverpool", TEAMS.replace_aliases("เป็ดแดงเตะวันไหน"))

    def test_live_team_refresh_keeps_offline_aliases(self):
        live = TeamDirectory.from_payload({"teams": [{"team_id": 57, "name": "Arsenal FC",
            "short_name": "Arsenal", "aliases": ["ใหม่"]}]})
        merged = TEAMS.merged(live)
        self.assertEqual(merged.find("ปืนใหญ่")[0].team_id, 57)
        self.assertEqual(merged.find("ใหม่")[0].team_id, 57)


class PlayerInfoTests(unittest.TestCase):
    """CONTRACT v1.5: the classifier (04) does not know player_info, so rules must catch it."""

    PLAYER_QUERIES = [
        ("อาร์เซนอลมีนักเตะใครบ้าง", [57]),
        ("ขอดูสควอดของเชลซีหน่อย", [61]),
        ("โค้ชของลิเวอร์พูลคือใคร", [64]),
        ("ผู้จัดการทีมแมนซิตี้คนปัจจุบันคือใคร", [65]),
        ("ซาก้าเล่นตำแหน่งอะไร", []),
        ("ฮาลันด์อายุเท่าไหร่", []),
        ("นักเตะสัญชาติไทยในพรีเมียร์ลีกมีใครบ้าง", []),
        ("ผู้รักษาประตูของนิวคาสเซิลมีใครบ้าง", [67]),
        ("Which players are in the Chelsea squad", [61]),
        ("What position does Salah play", []),
        ("Who is the manager of Arsenal", [57]),
        ("How old is Erling Haaland", []),
    ]

    def test_player_questions_route_to_player_documents(self):
        for query, team_ids in self.PLAYER_QUERIES:
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertIsNotNone(result)
                self.assertEqual(result.intent, "player_info")
                self.assertEqual(result.route, "football_rag")
                self.assertEqual(result.layer, "rules")
                self.assertEqual(result.filters["category"], ["player"])
                self.assertEqual(result.filters.get("team_ids", []), team_ids)
                self.assertNotIn("matchweek", result.filters)

    def test_player_rewrite_is_english_and_keeps_the_question(self):
        query = "อาร์เซนอลมีนักเตะใครบ้าง"
        result = decide(query, CONTEXT, [], TEAMS)
        self.assertIn("Arsenal", result.rewritten_query)
        self.assertIn("squad", result.rewritten_query)
        self.assertIn(query, result.rewritten_query)

    def test_neighbouring_questions_keep_their_intent(self):
        cases = [
            ("ใครนำดาวซัลโวตอนนี้", "standings_stats"),
            ("ดาวซัลโวของอาร์เซนอลคือใคร", "standings_stats"),
            ("อาร์เซนอลอยู่ตำแหน่งไหนในตารางคะแนน", "standings_stats"),
            ("ผู้รักษาประตูใช้มือได้ตอนไหน", "general_football"),
            ("ผู้เล่นคนไหนโดนใบแดงเมื่อวาน", "match_result"),
            ("โค้ชคนไหนพาทีมได้แชมป์พรีเมียร์ลีกมากที่สุด", "trivia_history"),
            ("นักเตะคนไหนยิงประตูมากที่สุดฤดูกาลนี้", "standings_stats"),
            # This question still falls through to the classifier/LLM.
            ("What position is Arsenal in the table", None),
        ]
        for query, intent in cases:
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(result.intent if result else None, intent)

    def test_classifier_and_llm_labels_map_to_player_documents(self):
        self.assertEqual(classify_intent("player_info", 0.8).filters, {"category": ["player"]})
        self.assertEqual(from_intent("player_info", 0.6).route, "football_rag")


class SeasonChanceTests(unittest.TestCase):
    def test_title_chance_without_mee_is_a_prediction(self):
        for query in ("โอกาสแชมป์ของอาร์เซนอล", "แล้วโอกาสแชมป์ของอาร์เซนอลล่ะ", "โอกาสตกชั้นของเบิร์นลีย์"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual((result.route, result.intent), ("local_ai", "prediction"))


class FollowUpWordingTests(unittest.TestCase):
    """Short and English questions that used to fall through to the classifier or land on trivia."""

    def intent(self, query):
        result = decide(query, CONTEXT, [], TEAMS)
        return result.intent if result else None

    def test_goal_count_and_scorer_questions_are_match_results(self):
        for query in ("นิวคาสเซิลยิงกี่ลูก", "ลิเวอร์พูลได้กี่ประตู", "เชลซียิงได้กี่ลูกเมื่อวาน", "ใครทำประตู",
                      "แล้วใครยิง", "who scored?", "who scored for Liverpool yesterday?",
                      "did Arsenal win?", "Who won Arsenal vs Chelsea yesterday?", "how did Chelsea do?"):
            with self.subTest(query=query):
                self.assertEqual(self.intent(query), "match_result")

    def test_next_match_questions_are_fixtures(self):
        for query in ("ลิเวอร์พูลนัดต่อไปเจอใคร", "ทีมนี้นัดต่อไปเตะกับใคร", "นัดถัดไปของเชลซีเตะเมื่อไหร่",
                      "อาร์เซนอลเจอใครต่อ", "when is the next match?", "who do Arsenal play next?",
                      "Chelsea next game"):
            with self.subTest(query=query):
                self.assertEqual(self.intent(query), "fixture_schedule")

    def test_top_of_the_table_is_standings(self):
        for query in ("who is top of the table?", "show me the league table"):
            with self.subTest(query=query):
                self.assertEqual(self.intent(query), "standings_stats")

    def test_records_and_history_stay_trivia(self):
        for query in ("ใครยิงแฮตทริกเร็วที่สุด", "ใครทำประตูมากที่สุดตลอดกาล", "ใครยิงประตูแรกในประวัติศาสตร์พรีเมียร์ลีก",
                      "who scored the fastest goal ever",
                      "ใครยิงให้ลิเวอร์พูลปี 2005", "who scored for Arsenal in 1998"):
            with self.subTest(query=query):
                self.assertEqual(self.intent(query), "trivia_history")
        # 2016 ended 2015/16 and began 2016/17: the rules ask which (user choice 2026-10-05).
        self.assertEqual(decide("who won the league in 2016", CONTEXT, [], TEAMS).route, "clarify")

    def test_top_scorer_questions_keep_their_intent(self):
        for query in ("ใครยิงเยอะสุด", "who scored the most goals this season"):
            with self.subTest(query=query):
                self.assertEqual(self.intent(query), "standings_stats")


class InternationalTriviaTests(unittest.TestCase):
    """Thai golden set (eval/golden_thai.jsonl): World Cup, Euro and national-team questions
    are history, and their search text must not be pushed toward the Premier League."""

    def decide(self, query):
        return decide(query, CONTEXT, [], TEAMS)

    def test_international_scorer_questions_are_trivia(self):
        for query in ("ใครทำประตูแรกในบอลโลกอะ?",
                      "ผู้ยิงประตูได้เยอะที่สุดของทีมชาติโปแลนด์คือใคร?",
                      "ทีมชาติอังกฤษผู้ยิงประตูเยอะสุดคือใครอะ?",
                      "ใครเป็นผู้ทำประตูสูงสุดของทีมซัมเบียตลอดมา?",
                      "ใครทำประตูครบร้อยในลีกสูงสุดอังกฤษก่อนคนอื่น?"):
            with self.subTest(query=query):
                result = self.decide(query)
                self.assertEqual((result.route, result.intent), ("football_rag", "trivia_history"))
                self.assertNotIn("matchweek", result.filters)

    def test_competition_names_go_into_the_search_text(self):
        cases = [("ใครได้แชมป์บอลโลกปี 1954 นะ", ("FIFA World Cup", "1954")),
                 ("ทีมไหนแชมป์ยุโรป 88?", ("UEFA",)),
                 ("คอนเฟดคัพปี 2003 ใครได้แชมป์", ("Confederations Cup", "2003")),
                 ("ทีมที่เป็นรองชนะเลิศยูฟ่าแชมเปียนส์ลีกปี 1980 คือทีมไหน?", ("Champions League", "1980"))]
        for query, terms in cases:
            with self.subTest(query=query):
                rewritten = self.decide(query).rewritten_query
                for term in terms:
                    self.assertIn(term, rewritten)
                self.assertNotIn("Premier League", rewritten)
                self.assertIn(query, rewritten)

    def test_trivia_without_a_known_competition_keeps_the_question_alone(self):
        # A generic English prefix pulled the same unrelated documents to the top
        # (Thai golden set: raw Thai found them, the prefixed text did not).
        for query in ("ทีมไหนเคยแชมป์ทวีปตั้งแต่ครั้งแรกจนถึงครั้งที่ห้าต่อเนื่อง?",
                      "ทีมชาติที่ฉายาซูเปอร์อีเกิ้ลส์คือประเทศอะไร",
                      "ใครเป็นผู้ทำประตูสูงสุดของทีมซัมเบียตลอดมา?"):
            with self.subTest(query=query):
                self.assertEqual(self.decide(query).rewritten_query, query)

    def test_premier_league_title_text_is_short(self):
        count = self.decide("อาร์เซนอลได้แชมป์พรีเมียร์ลีกกี่ครั้ง").rewritten_query
        self.assertEqual(count, "Arsenal Premier League title count อาร์เซนอลได้แชมป์พรีเมียร์ลีกกี่ครั้ง")
        # Without a team the Thai question already names the league; the prefix only hurt.
        query = "ทีมแรกที่ได้แชมป์พรีเมียร์ลีกโดยไม่ได้มาจากแมนเชสเตอร์หรือลอนดอนคือทีมไหน"
        self.assertEqual(self.decide(query).rewritten_query, query)

    def test_premier_league_questions_keep_their_routing(self):
        title = self.decide("อาร์เซนอลได้แชมป์พรีเมียร์ลีกกี่ครั้ง")
        self.assertEqual(title.intent, "trivia_history")
        self.assertIn("Premier League title", title.rewritten_query)
        self.assertEqual(self.decide("ใครยิงเยอะสุด").intent, "standings_stats")
        self.assertEqual(self.decide("ดาวซัลโวฟุตบอลโลกคือใคร").route, "decline")


if __name__ == "__main__":
    unittest.main()


class HistoricalDecisionTests(unittest.TestCase):
    def test_past_season_questions_search_the_archive_for_that_season(self):
        cases = (
            ("ใครได้แชมป์พรีเมียร์ลีกฤดูกาล 2004/05", "2004"),
            ("ฤดูกาล 98/99 ใครได้รองแชมป์พรีเมียร์ลีก", "1998"),
            ("ฤดูกาลที่แล้วใครได้แชมป์พรีเมียร์ลีก", "2025"),
            ("อาร์เซนอลจบอันดับเท่าไหร่ในฤดูกาล 2015/16", "2015"),
            ("เลสเตอร์ซิตี้ฤดูกาล 2015/16 ได้กี่แต้ม", "2015"),
            ("แบล็คเบิร์น โรเวอร์ส ฤดูกาล 1994/95 จบอันดับเท่าไหร่", "1994"),
            ("Bolton Wanderers 2005/06 final table position", "2005"),
            ("Who won the Premier League in 2004/05?", "2004"),
        )
        for query, season in cases:
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual((result.route, result.intent, result.layer),
                                 ("football_rag", "trivia_history", "rules"))
                self.assertEqual(result.filters, {"category": ["historical"], "season": season})

    def test_archive_search_names_teams_without_filtering_by_them(self):
        result = decide("อาร์เซนอลจบอันดับเท่าไหร่ในฤดูกาล 2015/16", CONTEXT, [], TEAMS)
        self.assertEqual(result.team_ids, [57])
        self.assertNotIn("team_ids", result.filters)
        self.assertIn("Premier League 2015/16 final table standings", result.rewritten_query)

    def test_head_to_head_questions_search_the_archive_without_a_season(self):
        for query in ("แมนยูเคยชนะลิเวอร์พูลกี่นัดในพรีเมียร์ลีก", "ลิเวอร์พูลกับเอฟเวอร์ตันเจอกันกี่ครั้ง",
                      "อาร์เซนอลกับเชลซี สถิติพบกันเป็นยังไง", "Arsenal vs Chelsea head to head"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertEqual(result.intent, "trivia_history")
                self.assertEqual(result.filters, {"category": ["historical"]})
                self.assertEqual(len(result.team_ids), 2)
        thai = decide("ลิเวอร์พูลกับเอฟเวอร์ตันเจอกันกี่ครั้ง", CONTEXT, [], TEAMS)
        self.assertIn("head-to-head", thai.rewritten_query)

    def test_season_label_crosses_the_century(self):
        result = decide("ฤดูกาล 1999/2000 ใครได้แชมป์พรีเมียร์ลีก", CONTEXT, [], TEAMS)
        self.assertEqual(result.filters["season"], "1999")
        self.assertIn("1999/00", result.rewritten_query)

    def test_questions_the_archive_must_not_take(self):
        for query in ("อาร์เซนอลอยู่อันดับเท่าไหร่", "ตารางคะแนนพรีเมียร์ลีกฤดูกาล 2026/27",
                      "ตารางคะแนนปี 2026", "ตารางคะแนนฤดูกาล 2030/31", "อาร์เซนอลกับเชลซีใครจะชนะ",
                      "ใครได้แชมป์บอลโลกปี 1954", "ใครได้บัลลงดอร์ปี 2008", "ใครได้แชมป์เอฟเอคัพปี 2005",
                      "ใครได้แชมป์ยูฟ่าแชมเปียนส์ลีกปี 2005", "เมื่อวานอาร์เซนอลชนะไหม",
                      "ลิเวอร์พูลชนะไปกี่นัดแล้วฤดูกาลนี้", "อาร์เซนอลเคยชนะกี่นัดติด"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual((result.filters if result else {}).get("category"), ["historical"])

    def test_without_a_current_season_past_years_are_not_assumed(self):
        self.assertIsNone(history_filters("ใครได้แชมป์ฤดูกาล 2004/05", 0, None))
        self.assertEqual(history_filters("อาร์เซนอลกับเชลซีสถิติพบกัน", 2, None),
                         {"category": ["historical"]})

    def test_other_history_searches_trivia_and_archive(self):
        self.assertEqual(classify_intent("trivia_history", 0.9).filters,
                         {"category": ["trivia", "historical"]})
        self.assertEqual(from_intent("trivia_history", 0.8).filters,
                         {"category": ["trivia", "historical"]})
        self.assertEqual(classify_intent("match_result", 0.9).filters, {"category": ["match_report"]})

    def test_nineties_short_season_for_scorers(self):
        self.assertEqual(historical_scorer_season("ดาวซัลโวพรีเมียร์ลีก 98/99", "2026"), ("1998", False))
        self.assertEqual(historical_scorer_season("ดาวซัลโวพรีเมียร์ลีก 24/25", "2026"), ("2024", False))

    def test_future_two_digit_seasons_are_not_last_century(self):
        self.assertEqual(historical_scorer_season("ดาวซัลโวฤดูกาล 27/28", "2026"), ("2027", False))
        for query in ("ตารางคะแนนฤดูกาล 27/28", "ใครแชมป์ฤดูกาล 27/28", "ตารางคะแนนฤดูกาล 30/31"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual((result.filters if result else {}).get("category"), ["historical"])

    def test_current_match_questions_between_two_teams_stay_current(self):
        for query in ("แมนยูกับลิเวอร์พูลนัดล่าสุดชนะกันกี่ลูก", "แมนยูเจอลิเวอร์พูลเมื่อวานชนะกันกี่ประตู",
                      "แมนยูกับลิเวอร์พูลเจอกันกี่โมง", "แมนยูเจอลิเวอร์พูลเจอกันกี่ครั้งฤดูกาลนี้"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual((result.filters if result else {}).get("category"), ["historical"])

    def test_other_competitions_never_search_only_the_league_archive(self):
        for query in ("แชมป์เอฟเอ คัพปี 2005", "แชมป์ถ้วยเอฟเอปี 2005", "แชมป์ efl cup ปี 2005",
                      "ใครแชมป์ไทยลีกปี 2010", "ใครแชมป์เอเชียนคัพปี 2007", "ใครได้แชมป์ซีเกมส์ปี 2005",
                      "ใครแชมป์ลีกกรีซฤดูกาล 2000/01", "บาร์เซโลน่าแชมป์ปี 2005"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual((result.filters if result else {}).get("category"), ["historical"])

    def test_seasons_before_the_premier_league_keep_trivia(self):
        for query in ("ลิเวอร์พูลแชมป์ปี 1990", "ใครแชมป์ดิวิชั่น 4 ฤดูกาล 1991/92"):
            with self.subTest(query=query):
                result = decide(query, CONTEXT, [], TEAMS)
                self.assertNotEqual((result.filters if result else {}).get("category"), ["historical"])

    def test_a_bare_year_searches_both_seasons_it_may_mean(self):
        result = decide("อาร์เซนอลได้แชมป์พรีเมียร์ลีกปี 2004 ไหม", CONTEXT, [], TEAMS)
        self.assertEqual(result.filters, {"category": ["historical"]})
        self.assertIn("2003/04", result.rewritten_query)
        self.assertIn("2004/05", result.rewritten_query)
        self.assertNotIn("head-to-head", result.rewritten_query)

    def test_archive_search_names_former_clubs_in_english(self):
        cases = (("แบล็คเบิร์น โรเวอร์ส ฤดูกาล 1994/95 จบอันดับเท่าไหร่", "Blackburn Rovers"),
                 ("เลสเตอร์ซิตี้ฤดูกาล 2015/16 ได้กี่แต้ม", "Leicester City"))
        for query, name in cases:
            with self.subTest(query=query):
                self.assertIn(name, decide(query, CONTEXT, [], TEAMS).rewritten_query)


class ChatDecisionTests(unittest.TestCase):
    def test_chat_cases(self):
        cases = [json.loads(line) for line in CHAT_CASES.read_text(encoding="utf-8").splitlines() if line]
        self.assertGreaterEqual(len(cases), 40)
        for case in cases:
            with self.subTest(query=case["query"]):
                result = decide(case["query"], CONTEXT, [], TEAMS)
                if case["kind"]:
                    self.assertIsNotNone(result)
                    self.assertEqual((result.route, result.intent, result.layer, result.kind),
                                     ("chat", "chitchat", "rules", case["kind"]))
                    self.assertEqual(result.reasoning, f"คุยทั่วไป: {case['kind']}")
                    self.assertEqual(result.filters, {})
                else:
                    self.assertTrue(result is None or result.route != "chat")

    def test_gambling_and_off_topic_stay_declined(self):
        for query in ("คุณช่วยเรื่องพนันได้ไหม", "แนะนำทีเด็ดหน่อยคุณ", "อากาศวันนี้ร้อนไหม"):
            with self.subTest(query=query):
                self.assertEqual(decide(query, CONTEXT, [], TEAMS).route, "decline")

    def test_mixed_questions_keep_their_football_route(self):
        self.assertEqual(decide("สวัสดี ลิเวอร์พูลชนะไหม", CONTEXT, [], TEAMS).route, "football_rag")
        self.assertEqual(decide("ขอบคุณครับ ผลนัดล่าสุดล่ะ", CONTEXT, [], TEAMS).route, "football_rag")

    def test_chitchat_label_maps_to_chat_and_the_switch_restores_decline(self):
        self.assertEqual(INTENT_MAP["chitchat"], ("chat", None))
        self.assertEqual(classify_intent("chitchat", 0.9).route, "chat")
        self.assertEqual(classify_intent("chitchat", 0.9).filters, {})
        self.assertEqual(from_intent("chitchat", 0.6).route, "chat")
        with patch.dict("os.environ", {"ROUTER_CHAT_ENABLED": "false"}):
            self.assertIsNone(decide("สวัสดีครับ", CONTEXT, [], TEAMS))
            self.assertEqual(classify_intent("chitchat", 0.9).route, "decline")
            self.assertEqual(from_intent("chitchat", 0.6).intent, "out_of_scope")

    def test_misspelled_football_words_do_not_make_chat(self):
        result = decide("ผีเเดงเคยได้แชมร์กี่ปี", CONTEXT, [], TEAMS)
        self.assertNotEqual(result.route, "chat")
