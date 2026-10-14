"""Club records and league honours computed from final tables (no network)."""

import re

import pytest

from app import history_records
from app.history_records import make_record_documents, ordinal

# Copied from 05's app/kb/documents.py (CONTRACT §6 v1.13) so 07 cannot drift from it.
HISTORICAL_ID = re.compile(
    r"hist-(?:season-\d{4}|team-\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*|h2h-[a-z0-9]+(?:-[a-z0-9]+)*"
    r"|club-[a-z0-9]+(?:-[a-z0-9]+)*|records)"
)

CLUBS = {
    "arsenal": {"name": "Arsenal FC", "team_id": 57},
    "chelsea": {"name": "Chelsea FC", "team_id": 61},
    "everton": {"name": "Everton FC", "team_id": 62},
    "leeds-united": {"name": "Leeds United FC", "team_id": None},
    "fulham": {"name": "Fulham FC", "team_id": 63},
    "wimbledon": {"name": "Wimbledon FC", "team_id": None},
    "bolton-wanderers": {"name": "Bolton Wanderers FC", "team_id": None},
    "ipswich-town": {"name": "Ipswich Town FC", "team_id": 349},
    "derby-county": {"name": "Derby County FC", "team_id": None},
}


def table(order, adjustments=None):
    """Final table in finishing order: n-i wins, i-1 losses, no draws."""
    n, rows = len(order), []
    for i, slug in enumerate(order, 1):
        adjustment = (adjustments or {}).get(slug, 0)
        gf, ga = 10 - i, i
        rows.append(
            {
                "club_slug": slug,
                "position": i,
                "played": n - 1,
                "wins": n - i,
                "draws": 0,
                "losses": i - 1,
                "goals_for": gf,
                "goals_against": ga,
                "goal_difference": gf - ga,
                "points": 3 * (n - i) + adjustment,
                "point_adjustment": adjustment,
            }
        )
    return rows


TABLES = {
    "2000": table(["arsenal", "chelsea", "everton", "leeds-united", "fulham", "wimbledon"]),
    "2001": table(
        ["chelsea", "arsenal", "everton", "bolton-wanderers", "ipswich-town", "derby-county"]
    ),
    "2002": table(
        ["arsenal", "everton", "chelsea", "leeds-united", "fulham", "bolton-wanderers"],
        {"leeds-united": -3},
    ),
}


def docs():
    return {d["doc_id"]: d for d in make_record_documents(TABLES, CLUBS)}


def body(doc):
    return doc["text"].split("\n## Sources and license\n", 1)[0]


def test_one_document_per_club_then_the_records_document():
    documents = make_record_documents(TABLES, CLUBS)
    assert [d["doc_id"] for d in documents] == [
        *(f"hist-club-{slug}" for slug in sorted(CLUBS)),
        "hist-records",
    ]
    assert all(HISTORICAL_ID.fullmatch(d["doc_id"]) for d in documents)


def test_metadata_and_license_follow_the_archive():
    for doc in make_record_documents(TABLES, CLUBS):
        assert doc["category"] == "historical"
        assert doc["origin"] == "fjelstul"
        assert doc["url"] == "https://github.com/jfjelstul/englishfootball"
        assert doc["season"] is doc["matchweek"] is doc["date"] is doc["fetched_at"] is None
        assert "Joshua C. Fjelstul, Ph.D." in doc["text"]
        coverage = "Coverage: Premier League statistics are for 2000/01 to 2002/03.\n"
        # The records document has no chunk of its own for the coverage line alone.
        first = "## Titles by club\n" if doc["topic"] == "league_records" else ""
        assert body(doc).startswith(first + coverage)
    d = docs()
    assert d["hist-club-arsenal"]["topic"] == "club_record"
    assert d["hist-club-arsenal"]["title"] == "Arsenal FC — Premier League record 2000/01–2002/03"
    assert d["hist-club-arsenal"]["team_ids"] == [57]
    assert d["hist-club-wimbledon"]["team_ids"] == []
    assert d["hist-records"]["topic"] == "league_records"
    assert d["hist-records"]["title"] == (
        "Premier League honours and all-time records 2000/01–2002/03"
    )
    assert d["hist-records"]["team_ids"] == [57, 61, 62, 63, 349]


def test_club_titles_runners_up_seasons_and_finishes():
    text = body(docs()["hist-club-arsenal"])
    assert "Premier League titles: 2 (2000/01, 2002/03).\n" in text
    assert "Runners-up: 1 (2001/02).\n" in text
    assert "Seasons in the Premier League: 3 of 3. Relegations: 0.\n" in text
    assert "Best finish: 1st (2 times). Worst finish: 2nd (2001/02).\n" in text
    assert "All-time Premier League record: P15 W14 D0 L1 GF26 GA4 GD+22 Pts42.\n" in text
    assert "## Finishes by season 2000/01–2002/03\n2000/01: 1st, 15 pts\n" in text


def test_club_without_titles_says_never_won():
    text = body(docs()["hist-club-everton"])
    assert "Premier League titles: 0 (never won the Premier League).\n" in text
    assert "Runners-up: 1 (2002/03).\n" in text
    derby = body(docs()["hist-club-derby-county"])
    assert "Runners-up: 0.\n" in derby
    assert "()" not in derby
    assert "Seasons in the Premier League: 1 of 3. Relegations: 1 (2001/02).\n" in derby
    assert "Best finish: 6th (1 time). Worst finish: 6th (2001/02).\n" in derby


def test_point_adjustment_is_kept_in_totals_and_finishes():
    text = body(docs()["hist-club-leeds-united"])
    assert "Relegations: 2 (2000/01, 2002/03).\n" in text
    assert "2002/03: 4th, 3 pts (point adjustment -3)\n" in text
    assert "All-time Premier League record: P10 W4 D0 L6 GF12 GA8 GD+4 Pts9.\n" in text


def test_finishes_split_into_groups(monkeypatch):
    monkeypatch.setattr(history_records, "GROUP", 2)
    text = body(docs()["hist-club-arsenal"])
    assert "## Finishes by season 2000/01–2001/02\n" in text
    assert "## Finishes by season 2002/03–2002/03\n" in text


def test_records_titles_champions_and_ever_present():
    text = body(docs()["hist-records"])
    assert "Arsenal FC 2 · Chelsea FC 1.\n" in text
    assert "2 different clubs have won the Premier League.\n" in text
    assert (
        "## Champions and runners-up 2000/01–2002/03\n"
        "2000/01: Arsenal FC (runners-up Chelsea FC)\n"
        "2001/02: Chelsea FC (runners-up Arsenal FC)\n"
        "2002/03: Arsenal FC (runners-up Everton FC)\n"
    ) in text
    assert (
        "## Ever-present clubs\nมี 3 ทีมที่อยู่พรีเมียร์ลีกครบทุกฤดูกาล (3 ฤดูกาล) และไม่เคยตกชั้น\n"
        "3 clubs have played in all 3 Premier League seasons: "
        "Arsenal FC, Chelsea FC, Everton FC.\n"
    ) in text


def test_records_all_time_table_breaks_ties_by_gd_gf_then_name():
    table_text = body(docs()["hist-records"]).split("## All-time table: positions 1-9\n", 1)[1]
    rows = [line for line in table_text.splitlines() if line[:1].isdigit()]
    names = [line.split(". ", 1)[1].split(":", 1)[0] for line in rows]
    assert names == [
        "Arsenal FC",
        "Chelsea FC",
        "Everton FC",
        "Leeds United FC",
        "Bolton Wanderers FC",
        "Fulham FC",
        "Ipswich Town FC",
        "Derby County FC",
        "Wimbledon FC",
    ]
    assert table_text.startswith(
        "ตารางคะแนนรวมตลอดกาลของพรีเมียร์ลีก ทีมที่เก็บแต้มรวมมากที่สุดคือ Arsenal FC (42 แต้ม)\n"
        "1. Arsenal FC: P15 W14 D0 L1 GF26 GA4 GD+22 Pts42\n"
    )


def test_records_grammar_for_a_single_club():
    tables = {
        "2000": table(["arsenal", "chelsea", "everton", "leeds-united"]),
        "2001": table(["arsenal", "fulham", "wimbledon", "derby-county"]),
    }
    text = body(make_record_documents(tables, CLUBS)[-1])
    assert "1 different club has won the Premier League.\n" in text
    assert "1 club has played in all 2 Premier League seasons: Arsenal FC.\n" in text


@pytest.mark.parametrize(
    ("n", "label"),
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
    ],
)
def test_ordinal(n, label):
    assert ordinal(n) == label


def test_club_summary_sentence_in_english_only():
    # Thai text here outranked head-to-head documents for Thai questions (eval 2026-10-04).
    d = docs()
    arsenal = body(d["hist-club-arsenal"])
    assert "Arsenal FC have won the Premier League title 2 times.\n" in arsenal
    assert "Chelsea FC have won the Premier League title once.\n" in body(d["hist-club-chelsea"])
    assert "Everton FC have never won the Premier League title.\n" in body(d["hist-club-everton"])
    assert not any(
        "฀" <= ch <= "๿"
        for doc in d.values()
        if doc["topic"] == "club_record"
        for ch in doc["text"]
    )


def test_records_summary_sentences_in_english_and_thai():
    text = body(docs()["hist-records"])
    assert (
        "2000/01 to 2002/03.\nMost Premier League titles: Arsenal FC (2).\n"
        "ทีมที่ได้แชมป์พรีเมียร์ลีกมากที่สุดคือ Arsenal FC (2 สมัย) "
        "มีทั้งหมด 2 ทีมที่เคยได้แชมป์พรีเมียร์ลีก\nArsenal FC 2 · Chelsea FC 1.\n"
    ) in text


def test_records_summary_lists_every_club_tied_on_most_titles():
    tables = {
        "2000": table(["arsenal", "everton", "leeds-united", "fulham"]),
        "2001": table(["chelsea", "wimbledon", "derby-county", "bolton-wanderers"]),
    }
    text = body(make_record_documents(tables, CLUBS)[-1])
    assert "Most Premier League titles: Arsenal FC, Chelsea FC (1).\n" in text
    assert "ทีมที่ได้แชมป์พรีเมียร์ลีกมากที่สุดคือ Arsenal FC, Chelsea FC (1 สมัย)" in text
    assert "## Ever-present clubs\nไม่มีทีมใดอยู่พรีเมียร์ลีกครบทุกฤดูกาล\n" in text


def test_ever_present_club_relegated_in_the_last_season_is_not_called_never_relegated():
    tables = {
        "2000": table(["arsenal", "chelsea", "everton", "leeds-united", "fulham", "wimbledon"]),
        "2001": table(
            ["arsenal", "chelsea", "bolton-wanderers", "everton", "fulham", "derby-county"]
        ),
    }
    text = body(make_record_documents(tables, CLUBS)[-1])
    # Arsenal, Chelsea, Everton and Fulham play both seasons; Everton go down in the last one.
    assert "มี 4 ทีมที่อยู่พรีเมียร์ลีกครบทุกฤดูกาล (2 ฤดูกาล)\n" in text
    assert "ไม่เคยตกชั้น" not in text


# Live chat test 2026-10-04: questions on relegations, total points and unbeaten seasons found
# nothing, because the documents lacked the words people search with (relegated, points).
def test_club_record_sentence_uses_the_words_people_ask_with():
    d = docs()
    assert (
        "Arsenal FC have won the Premier League title 2 times.\n"
        "Arsenal FC finished runner-up once, were never relegated and played 3 of 3 "
        "Premier League seasons. Total Premier League points: 42.\n"
        "Unbeaten Premier League seasons (no defeats): 2000/01, 2002/03.\n"
        "Premier League titles: 2"
    ) in body(d["hist-club-arsenal"])
    leeds = body(d["hist-club-leeds-united"])
    assert (
        "Leeds United FC never finished runner-up, were relegated 2 times and played 2 of 3 "
        "Premier League seasons. Total Premier League points: 9.\n"
    ) in leeds
    assert "Unbeaten" not in leeds
    derby = body(d["hist-club-derby-county"])
    assert "were relegated once and played 1 of 3 Premier League seasons." in derby


def test_records_all_time_records_section():
    # One record per heading, so each is a short chunk like the trivia it competes with.
    text = body(docs()["hist-records"])
    assert (
        "## Record: most all-time Premier League points\n"
        "Which club has the most all-time Premier League points? Arsenal FC (42).\n"
        "## Record: most Premier League runner-up finishes\n"
        "Which club has finished runner-up the most times in the Premier League? "
        "Arsenal FC, Chelsea FC, Everton FC (1).\n"
        "## Record: most Premier League relegations\n"
        "Which club has been relegated from the Premier League the most times? "
        "Bolton Wanderers FC, Fulham FC, Leeds United FC (2).\n"
        "## Record: unbeaten Premier League seasons\n"
        "Which club went a whole Premier League season unbeaten? Arsenal FC 2000/01, "
        "Chelsea FC 2001/02, Arsenal FC 2002/03.\n"
        "## Champions and runners-up"
    ) in text


def test_records_without_an_unbeaten_season_say_so():
    tables = {"2000": table(["arsenal", "chelsea", "everton", "leeds-united"])}
    tables["2000"][0]["losses"] = 1
    text = body(make_record_documents(tables, CLUBS)[-1])
    assert "Which club went a whole Premier League season unbeaten? None.\n" in text


# Live chat test 2026-10-04: trivia chunks phrased as questions ("Which team has the most …",
# "How many …") outranked the record lines, so the records read the same way.
def test_club_record_opens_with_the_question_people_ask():
    d = docs()
    assert body(d["hist-club-arsenal"]).startswith(
        "Coverage: Premier League statistics are for 2000/01 to 2002/03.\n"
        "How many Premier League titles have Arsenal FC won? 2 (2000/01, 2002/03).\n"
        "Arsenal FC have won the Premier League title 2 times.\n"
    )
    assert "How many Premier League titles have Everton FC won? None.\n" in body(
        d["hist-club-everton"]
    )


def early_entry(champion, runner_up):
    def team(t):
        slug, name = t
        return {"slug": slug, "name": CLUBS[slug]["name"] if slug else name}

    return {"champion": team(champion), "runner_up": team(runner_up)}


PRESTON = (None, "Preston North End")
EARLY = {
    "1912": early_entry(PRESTON, ("everton", None)),
    "1913": early_entry(("everton", None), ("arsenal", None)),
    "1914": early_entry(("arsenal", None), ("chelsea", None)),
    "1919": early_entry(("everton", None), PRESTON),
}


def early_docs(early=EARLY):
    return {d["doc_id"]: d for d in make_record_documents(TABLES, CLUBS, early)}


# Live chat test 2026-10-04: all-era lines in the first chunk made it long enough that its
# Premier League facts (relegations, never won) stopped ranking. They have their own heading.
def first_chunk(doc):
    return body(doc).split("\n## ", 1)[0]


def test_first_chunk_keeps_the_short_coverage_line():
    for doc in early_docs().values():
        assert (
            body(doc).count("Coverage: Premier League statistics are for 2000/01 to 2002/03.\n")
            == 1
        )
        assert "First Division titles before" not in first_chunk(doc)
        assert "All eras count" not in first_chunk(doc)


# Review 2026-10-04: a first chunk saying only "never won the Premier League title" could
# make the chat say Everton never won the league. It now gives the all-era count too.
def test_first_chunk_points_to_titles_in_all_eras():
    d = early_docs()
    assert (
        "How many Premier League titles have Everton FC won? None. "
        "English top-flight league titles in all eras: 2 (see below).\n"
    ) in first_chunk(d["hist-club-everton"])
    assert (
        "How many Premier League titles have Arsenal FC won? 2 (2000/01, 2002/03). "
        "English top-flight league titles in all eras: 3 (see below).\n"
    ) in first_chunk(d["hist-club-arsenal"])
    leeds = first_chunk(d["hist-club-leeds-united"])
    assert "How many Premier League titles have Leeds United FC won? None.\n" in leeds
    assert "in all eras" not in leeds
    assert "in all eras" not in first_chunk(docs()["hist-club-everton"])


def test_club_all_era_line_for_each_case():
    d = early_docs()
    arsenal = body(d["hist-club-arsenal"])
    assert (
        "## English top-flight league titles (all eras)\n"
        "How many English top-flight league titles have Arsenal FC won in all eras? "
        "3 (1 First Division, 2 Premier League).\n"
        "First Division titles before the Premier League: 1 (1914/15).\n"
        "All eras count First Division titles from 1912/13 to 1919/20 and Premier League titles.\n"
        "## Finishes by season"
    ) in arsenal
    everton = body(d["hist-club-everton"])
    assert "won in all eras? 2 (2 First Division, 0 Premier League).\n" in everton
    assert "First Division titles before the Premier League: 2 (1913/14, 1919/20).\n" in everton
    chelsea = body(d["hist-club-chelsea"])
    assert "won in all eras? 1 (0 First Division, 1 Premier League).\n" in chelsea
    assert "First Division titles before" not in chelsea
    leeds = body(d["hist-club-leeds-united"])
    assert (
        "How many English top-flight league titles have Leeds United FC won in all eras? None.\n"
        in leeds
    )
    assert "First Division titles before" not in leeds


def test_records_all_era_sections():
    text = body(early_docs()["hist-records"])
    assert (
        "## Record: most English top-flight league titles (all eras)\n"
        "Which club has won the most English top-flight league titles in all eras? "
        "Arsenal FC (3).\n"
        "## English top-flight league titles by club (all eras)\n"
        "Arsenal FC 3 (1 First Division + 2 Premier League) · "
        "Everton FC 2 (2 First Division + 0 Premier League) · "
        "Chelsea FC 1 (0 First Division + 1 Premier League) · "
        "Preston North End 1 (1 First Division + 0 Premier League).\n"
        "4 different clubs have been English top-flight champions.\n"
        "## First Division champions and runners-up 1912/13–1919/20\n"
        "1912/13: Preston North End (runners-up Everton FC)\n"
        "1913/14: Everton FC (runners-up Arsenal FC)\n"
        "1914/15: Arsenal FC (runners-up Chelsea FC)\n"
    ) in text
    assert text.index("## Record: unbeaten") < text.index("## Record: most English top-flight")
    assert text.index("## First Division champions") < text.index("## Champions and runners-up")


def test_first_division_section_marks_the_war_gap():
    text = body(early_docs()["hist-records"])
    assert (
        "1914/15: Arsenal FC (runners-up Chelsea FC)\n"
        "No First Division football 1915/16–1918/19 (First World War).\n"
        "1919/20: Everton FC (runners-up Preston North End)\n"
    ) in text
    late = {
        "1938": early_entry(("arsenal", None), ("everton", None)),
        "1946": early_entry(("everton", None), ("arsenal", None)),
    }
    assert "No First Division football 1939/40–1945/46 (Second World War).\n" in body(
        make_record_documents(TABLES, CLUBS, late)[-1]
    )


def test_first_division_section_splits_into_groups(monkeypatch):
    monkeypatch.setattr(history_records, "GROUP", 2)
    text = body(early_docs()["hist-records"])
    assert "## First Division champions and runners-up 1912/13–1913/14\n" in text
    assert "## First Division champions and runners-up 1914/15–1919/20\n" in text


def test_all_era_leaders_list_every_tied_club():
    early = {**EARLY, "1920": early_entry(("everton", None), ("arsenal", None))}
    text = body(early_docs(early)["hist-records"])
    assert "in all eras? Arsenal FC, Everton FC (3).\n" in text


# Wikidata counts First Division titles from 1892/93 only (Everton 8, Preston 0); before that
# the Football League had a single division. The records count those champions, and say so.
SINGLE_DIVISION_NOTE = (
    "Before 1892/93 the Football League had a single division; its champions are counted "
    "here as First Division champions."
)


def test_single_division_seasons_are_explained_when_present():
    early = {"1888": early_entry(PRESTON, ("everton", None)), **EARLY}
    d = early_docs(early)
    assert (
        "All eras count First Division titles from 1888/89 to 1919/20 and Premier League "
        "titles. " + SINGLE_DIVISION_NOTE + "\n"
    ) in body(d["hist-club-arsenal"])
    assert SINGLE_DIVISION_NOTE not in first_chunk(d["hist-club-arsenal"])
    assert "5 different clubs have been English top-flight champions.\n" not in body(
        d["hist-records"]
    )
    assert (
        "4 different clubs have been English top-flight champions. " + SINGLE_DIVISION_NOTE + "\n"
    ) in body(d["hist-records"])
    assert SINGLE_DIVISION_NOTE not in "".join(doc["text"] for doc in early_docs().values())


# Live chat test 2026-10-04: "แชมป์ปี 2025" found nothing; a calendar year spans two seasons.
def test_records_answer_the_champion_of_a_calendar_year():
    text = body(docs()["hist-records"])
    assert (
        "## Premier League champions by year 2000–2003\n"
        "Who won the Premier League in 2000? 2000/01 (began in 2000): Arsenal FC.\n"
        "Who won the Premier League in 2001? 2000/01 (ended in 2001): Arsenal FC · "
        "2001/02 (began in 2001): Chelsea FC.\n"
        "Who won the Premier League in 2002? 2001/02 (ended in 2002): Chelsea FC · "
        "2002/03 (began in 2002): Arsenal FC.\n"
        "Who won the Premier League in 2003? 2002/03 (ended in 2003): Arsenal FC.\n"
    ) in text


def test_champions_by_year_split_into_groups(monkeypatch):
    monkeypatch.setattr(history_records, "GROUP", 3)
    text = body(docs()["hist-records"])
    assert "## Premier League champions by year 2000–2002\n" in text
    assert "## Premier League champions by year 2003–2003\n" in text


def test_without_early_there_is_no_all_era_text():
    for doc in make_record_documents(TABLES, CLUBS):
        assert "all eras" not in doc["text"]
        assert "First Division champions" not in doc["text"]
