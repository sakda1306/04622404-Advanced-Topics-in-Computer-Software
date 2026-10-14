"""Premier League club records and league-wide honours, computed from the final tables."""

from collections import Counter, defaultdict

from app.history import FIELDS, historical_document, relegated, season_label, table_stats

FJELSTUL_URL = "https://github.com/jfjelstul/englishfootball"
GROUP = 10  # rows per heading, sized for retrieval's heading-based chunker
# The First Division began in 1892/93; Wikidata leaves the earlier champions out of it.
FIRST_DIVISION_FROM = "1892"
SINGLE_DIVISION_NOTE = (
    "Before 1892/93 the Football League had a single division; its champions are counted "
    "here as First Division champions."
)


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _labels(seasons: list[str]) -> str:
    return ", ".join(season_label(s) for s in seasons)


def _counted(label: str, seasons: list[str]) -> str:
    return f"{label}: {len(seasons)}" + (f" ({_labels(seasons)})" if seasons else "") + "."


def _subject(n: int, noun: str) -> str:
    return f"{n} {noun}s have" if n != 1 else f"{n} {noun} has"


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def _leaders(counts: dict, name) -> str:
    """Every club tied on the highest count, by name, then the count: "A, B (3)"."""
    most = max(counts.values())
    return ", ".join(sorted((name(s) for s, n in counts.items() if n == most))) + f" ({most})"


def _totals(rows: list[dict]) -> dict:
    return {field: sum(row[field] for row in rows) for field in FIELDS}


def _groups(items: list) -> list[list]:
    return [items[offset : offset + GROUP] for offset in range(0, len(items), GROUP)]


def make_record_documents(tables: dict, clubs: dict, early: dict | None = None) -> list[dict]:
    seasons = sorted(tables)
    first, last = season_label(seasons[0]), season_label(seasons[-1])
    span = f"{first}–{last}"
    # Short on purpose: it opens every first chunk, and a longer first chunk stopped ranking.
    coverage = f"Coverage: Premier League statistics are for {first} to {last}.\n"
    era_note = None
    if early:
        era_note = (
            f"All eras count First Division titles from {season_label(min(early))} to "
            f"{season_label(max(early))} and Premier League titles."
            + (f" {SINGLE_DIVISION_NOTE}" if min(early) < FIRST_DIVISION_FROM else "")
        )
    history = defaultdict(list)  # slug -> [(season, row, relegated?)] in season order
    for season in seasons:
        down = {row["club_slug"] for row in relegated(season, tables[season])}
        for row in sorted(tables[season], key=lambda r: r["position"]):
            history[row["club_slug"]].append((season, row, row["club_slug"] in down))
    # First Division titles by club; a club that never reached the Premier League keys by name.
    early_titles = defaultdict(list)
    for season, places in sorted((early or {}).items()):
        team = places["champion"]
        early_titles[team["slug"] or team["name"]].append(season)
    documents = [
        _club_document(
            slug,
            history[slug],
            clubs,
            coverage,
            span,
            len(seasons),
            early_titles.get(slug, []) if early else None,
            era_note,
        )
        for slug in sorted(history)
    ]
    documents.append(
        _records_document(seasons, tables, history, clubs, coverage, span, early, early_titles)
    )
    return documents


def _club_document(slug, entries, clubs, coverage, span, total, early_titles, era_note) -> dict:
    name = clubs[slug]["name"]
    titles = [s for s, row, _ in entries if row["position"] == 1]
    runners_up = [s for s, row, _ in entries if row["position"] == 2]
    relegations = [s for s, _, down in entries if down]
    positions = [row["position"] for _, row, _ in entries]
    best, worst = min(positions), max(positions)
    best_count = positions.count(best)
    # A plain sentence so keyword search matches how fans ask. English only: the router names
    # the club in English, and Thai text here outranked head-to-head documents (eval 2026-10-04).
    totals = _totals([row for _, row, _ in entries])
    # Phrased like the question: trivia chunks written as questions outranked plain labels.
    all_eras = len(early_titles) + len(titles) if early_titles is not None else 0
    text = (
        coverage
        + f"How many Premier League titles have {name} won? "
        + (f"{len(titles)} ({_labels(titles)})." if titles else "None.")
        # Alone, "never won the Premier League" could read as never champions of England.
        + (
            f" English top-flight league titles in all eras: {all_eras} (see below)."
            if all_eras
            else ""
        )
        + "\n"
    )
    text += (
        f"{name} have won the Premier League title {_times(len(titles))}.\n"
        if titles
        else f"{name} have never won the Premier League title.\n"
    )
    # Use the words people search with (runner-up, relegated, points), not only the labels below.
    text += (
        f"{name} "
        + (
            f"finished runner-up {_times(len(runners_up))}"
            if runners_up
            else "never finished runner-up"
        )
        + ", "
        + (f"were relegated {_times(len(relegations))}" if relegations else "were never relegated")
        + f" and played {len(entries)} of {total} Premier League seasons. "
        + f"Total Premier League points: {totals['points']}.\n"
    )
    unbeaten = [s for s, row, _ in entries if row["losses"] == 0]
    if unbeaten:
        text += f"Unbeaten Premier League seasons (no defeats): {_labels(unbeaten)}.\n"
    text += (
        _counted("Premier League titles", titles)
        if titles
        else "Premier League titles: 0 (never won the Premier League)."
    )
    text += "\n" + _counted("Runners-up", runners_up)
    text += f"\nSeasons in the Premier League: {len(entries)} of {total}. "
    text += _counted("Relegations", relegations)
    text += (
        f"\nBest finish: {ordinal(best)} ({best_count} time{'s' if best_count != 1 else ''}). "
        f"Worst finish: {ordinal(worst)} "
        f"({_labels([s for s, row, _ in entries if row['position'] == worst])}).\n"
    )
    text += f"All-time Premier League record: {table_stats(totals)}.\n"
    if early_titles is not None:
        # Its own heading, so the first chunk stays short (see the Coverage line).
        text += "## English top-flight league titles (all eras)\n"
        text += f"How many English top-flight league titles have {name} won in all eras? " + (
            f"{all_eras} ({len(early_titles)} First Division, {len(titles)} Premier League).\n"
            if all_eras
            else "None.\n"
        )
        if early_titles:
            text += (
                "First Division titles before the Premier League: "
                f"{len(early_titles)} ({_labels(early_titles)}).\n"
            )
        text += f"{era_note}\n"
    for group in _groups(entries):
        text += f"## Finishes by season {season_label(group[0][0])}–{season_label(group[-1][0])}\n"
        text += "".join(
            f"{season_label(s)}: {ordinal(row['position'])}, {row['points']} pts"
            + (
                f" (point adjustment {row['point_adjustment']})"
                if row.get("point_adjustment")
                else ""
            )
            + "\n"
            for s, row, _ in group
        )
    return historical_document(
        clubs,
        f"hist-club-{slug}",
        f"{name} — Premier League record {span}",
        text,
        "club_record",
        None,
        [slug],
        "fjelstul",
        FJELSTUL_URL,
    )


def _records_document(seasons, tables, history, clubs, coverage, span, early, early_titles) -> dict:
    def name(slug):
        return clubs[slug]["name"]

    def at(season, position):
        return next(r["club_slug"] for r in tables[season] if r["position"] == position)

    champions = Counter(at(s, 1) for s in seasons)
    ranked = sorted(champions.items(), key=lambda item: (-item[1], name(item[0])))
    most = ranked[0][1]
    leaders = ", ".join(name(slug) for slug, count in ranked if count == most)
    # Coverage under the first heading: alone above it, it became a chunk with nothing else.
    text = "## Titles by club\n" + coverage
    text += f"Most Premier League titles: {leaders} ({most}).\n"
    text += (
        f"ทีมที่ได้แชมป์พรีเมียร์ลีกมากที่สุดคือ {leaders} ({most} สมัย) "
        f"มีทั้งหมด {len(champions)} ทีมที่เคยได้แชมป์พรีเมียร์ลีก\n"
    )
    text += " · ".join(f"{name(slug)} {count}" for slug, count in ranked) + ".\n"
    text += f"{_subject(len(champions), 'different club')} won the Premier League.\n"
    totals = {slug: _totals([row for _, row, _ in e]) for slug, e in history.items()}
    unbeaten = [
        f"{name(row['club_slug'])} {season_label(s)}"
        for s in seasons
        for row in sorted(tables[s], key=lambda r: r["position"])
        if row["losses"] == 0
    ]
    # Each record reads as the question fans ask, with its answer, like the trivia it competes with.
    # One record per heading: the chunker splits on headings, and a short chunk with one
    # question ranks like the trivia it competes with; four records in one chunk ranked lower.
    points = {slug: t["points"] for slug, t in totals.items()}
    text += (
        "## Record: most all-time Premier League points\n"
        f"Which club has the most all-time Premier League points? {_leaders(points, name)}.\n"
    )
    runners_up = Counter(at(s, 2) for s in seasons)
    text += (
        "## Record: most Premier League runner-up finishes\n"
        "Which club has finished runner-up the most times in the Premier League? "
        f"{_leaders(runners_up, name)}.\n"
    )
    downs = Counter(s for s, e in history.items() for _, _, down in e if down)
    if downs:
        text += (
            "## Record: most Premier League relegations\n"
            "Which club has been relegated from the Premier League the most times? "
            f"{_leaders(downs, name)}.\n"
        )
    text += (
        "## Record: unbeaten Premier League seasons\n"
        "Which club went a whole Premier League season unbeaten? "
        + (", ".join(unbeaten) if unbeaten else "None")
        + ".\n"
    )
    if early:
        text += _all_era_sections(early, early_titles, champions, clubs)
    for group in _groups(seasons):
        text += f"## Champions and runners-up {season_label(group[0])}–{season_label(group[-1])}\n"
        text += "".join(
            f"{season_label(s)}: {name(at(s, 1))} (runners-up {name(at(s, 2))})\n" for s in group
        )
    # "แชมป์ปี 2025" names a calendar year, which ends one season and starts the next.
    years = list(range(int(seasons[0]), int(seasons[-1]) + 2))
    for group in _groups(years):
        text += f"## Premier League champions by year {group[0]}–{group[-1]}\n"
        for year in group:
            parts = [
                f"{season_label(str(s))} ({when} in {year}): {name(at(str(s), 1))}"
                for s, when in ((year - 1, "ended"), (year, "began"))
                if str(s) in tables
            ]
            text += f"Who won the Premier League in {year}? " + " · ".join(parts) + ".\n"
    ever = sorted((s for s, e in history.items() if len(e) == len(seasons)), key=name)
    # Ever-present clubs can still be relegated in the last archived season.
    never_down = not any(down for s in ever for _, _, down in history[s])
    text += "## Ever-present clubs\n" + (
        f"มี {len(ever)} ทีมที่อยู่พรีเมียร์ลีกครบทุกฤดูกาล ({len(seasons)} ฤดูกาล)"
        + (" และไม่เคยตกชั้น" if never_down else "")
        + "\n"
        f"{_subject(len(ever), 'club')} played in all {len(seasons)} Premier League seasons: "
        + ", ".join(name(s) for s in ever)
        + ".\n"
        if ever
        else "ไม่มีทีมใดอยู่พรีเมียร์ลีกครบทุกฤดูกาล\n"
        f"No club has played in all {len(seasons)} Premier League seasons.\n"
    )
    order = sorted(
        totals,
        key=lambda s: (
            -totals[s]["points"],
            -totals[s]["goal_difference"],
            -totals[s]["goals_for"],
            name(s),
        ),
    )
    for index, group in enumerate(_groups(order)):
        start = index * GROUP + 1
        text += f"## All-time table: positions {start}-{start + len(group) - 1}\n"
        if index == 0:
            text += (
                "ตารางคะแนนรวมตลอดกาลของพรีเมียร์ลีก ทีมที่เก็บแต้มรวมมากที่สุดคือ "
                f"{name(order[0])} ({totals[order[0]]['points']} แต้ม)\n"
            )
        text += "".join(
            f"{start + i}. {name(s)}: {table_stats(totals[s])}\n" for i, s in enumerate(group)
        )
    return historical_document(
        clubs,
        "hist-records",
        f"Premier League honours and all-time records {span}",
        text,
        "league_records",
        None,
        sorted(history),
        "fjelstul",
        FJELSTUL_URL,
    )


WARS = ((1915, 1918, "First World War"), (1939, 1945, "Second World War"))


def _all_era_sections(early: dict, early_titles: dict, champions: Counter, clubs: dict) -> str:
    """Top-flight titles in all eras, then First Division champions by season (with war gaps)."""

    def display(key):
        return clubs[key]["name"] if key in clubs else key

    keys = set(early_titles) | set(champions)
    counts = {k: len(early_titles.get(k, [])) + champions.get(k, 0) for k in keys}
    ranked = sorted(counts, key=lambda k: (-counts[k], display(k)))
    text = (
        "## Record: most English top-flight league titles (all eras)\n"
        "Which club has won the most English top-flight league titles in all eras? "
        f"{_leaders(counts, display)}.\n"
        "## English top-flight league titles by club (all eras)\n"
        + " · ".join(
            f"{display(k)} {counts[k]} ({len(early_titles.get(k, []))} First Division + "
            f"{champions.get(k, 0)} Premier League)"
            for k in ranked
        )
        + ".\n"
        + f"{_subject(len(keys), 'different club')} been English top-flight champions."
        + (f" {SINGLE_DIVISION_NOTE}" if min(early) < FIRST_DIVISION_FROM else "")
        + "\n"
    )
    previous = None
    for group in _groups(sorted(early)):
        text += (
            "## First Division champions and runners-up "
            f"{season_label(group[0])}–{season_label(group[-1])}\n"
        )
        for season in group:
            # Say when there was no football, so a question about 1942 finds an answer.
            for start, end, war in WARS:
                if previous is not None and int(previous) < start <= int(season):
                    text += (
                        f"No First Division football {season_label(str(start))}–"
                        f"{season_label(str(end))} ({war}).\n"
                    )
            places = early[season]
            text += (
                f"{season_label(season)}: {places['champion']['name']} "
                f"(runners-up {places['runner_up']['name']})\n"
            )
            previous = season
    return text
