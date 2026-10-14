"""Pinned Football.TXT parsing and historical table verification (no live APIs)."""

import csv
import json
import re
from collections import defaultdict
from datetime import date
from functools import partial
from pathlib import Path

SCORER_REFERENCE_PATH = Path(__file__).parents[1] / "data/scorer_reference.json"


def verified_season_top_scorer(season: str) -> dict | None:
    """Return only a curated Premier League winner with an official source URL."""
    reference = json.loads(SCORER_REFERENCE_PATH.read_text(encoding="utf-8"))
    record = reference.get(season)
    if not record:
        return None
    podium = record.get("top3") or []
    winner = record.get("winner_full_name")
    url = record.get("url")
    if (
        len(podium) < 2
        or any(not isinstance(entry, (list, tuple)) or len(entry) < 2 for entry in podium[:2])
        or not isinstance(winner, str)
        or not winner.strip()
        or not winner.casefold().endswith(str(podium[0][0]).casefold())
        or not isinstance(podium[0][1], int)
        or not isinstance(podium[1][1], int)
        or podium[0][1] < podium[1][1]
        or not isinstance(url, str)
        or not url.startswith("https://www.premierleague.com/")
    ):
        raise ValueError("Historical top-scorer reference is invalid")
    if podium[0][1] == podium[1][1]:
        return None
    return {
        "season": season,
        "season_label": f"{season}/{(int(season) + 1) % 100:02d}",
        "player": winner,
        "goals": podium[0][1],
        "source_url": url,
    }


MONTHS = {
    name: n
    for n, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
    )
}
DATE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$"
)
ROUND = re.compile(r"^▪\s*(?:Matchday\s+|Regular Season\s*-\s*)(\d+)")
SCORE = re.compile(r"^(.*?)\s+(\d+)-(\d+)(?:\s+\(\d+-\d+\))?\s+(.+?)\s*$")
VERSUS = re.compile(r"^(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)(?:\s+\(\d+-\d+\))?\s*$")
TIME = re.compile(r"^(\d{1,2}:\d{2})\s+")
FIELDS = (
    "played",
    "wins",
    "draws",
    "losses",
    "goals_for",
    "goals_against",
    "goal_difference",
    "points",
)


def parse_season(text: str, year: int) -> list[dict]:
    matches, day, week, clock = [], None, None, None
    scorer_block = False
    scorer_lines = []
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if scorer_block or line.startswith("("):
            if not matches:
                raise ValueError("Scorer block without a match")
            scorer_lines.append(line)
            scorer_block = not line.endswith(")")
            if not scorer_block:
                matches[-1]["goals"] = parse_goal_block(" ".join(scorer_lines), matches[-1])
                scorer_lines = []
            continue
        if not line or line.startswith(("#", "=", "(", ")")):
            continue
        round_match = ROUND.match(line)
        if round_match:
            week = int(round_match[1])
            continue
        date_match = DATE.match(line)
        if date_match:
            month = MONTHS[date_match[1]]
            # The 2019/20 COVID-delayed season continued into July 2020.
            date_year = int(date_match[3]) if date_match[3] else year + (month < 8)
            if date_year not in (year, year + 1):
                raise ValueError(f"{year}:{number}: date outside season")
            day = date(
                date_year,
                month,
                int(date_match[2]),
            ).isoformat()
            clock = None
            continue
        time_match = TIME.match(line)
        if time_match:
            clock = time_match[1]
            line = line[time_match.end() :]
        versus = VERSUS.match(line)
        standard = SCORE.match(line)
        if versus:
            home, away, hg, ag = versus.groups()
        elif standard:
            home, hg, ag, away = standard.groups()
        else:
            raise ValueError(f"{year}:{number}: unrecognized line: {line}")
        if day is None or week is None:
            raise ValueError(f"{year}:{number}: match has no date/round")
        matches.append(
            {
                "season": str(year),
                "matchweek": week,
                "date": day,
                "local_time": clock,
                "home": home.strip(),
                "away": away.strip(),
                "home_goals": int(hg),
                "away_goals": int(ag),
            }
        )
    if scorer_block:
        raise ValueError(f"{year}: unterminated scorer block")
    header = re.search(r"^# Matches\s+(\d+)", text, re.M)
    expected = int(header[1]) if header else (462 if year <= 1994 else 380)
    if len(matches) != expected:
        raise ValueError(f"{year}: parsed {len(matches)} matches; expected {expected}")
    pairs = [(m["home"], m["away"]) for m in matches]
    if len(pairs) != len(set(pairs)):
        raise ValueError(f"{year}: duplicate home/away pairing")
    return matches


def resolve(name: str, clubs: dict) -> str:
    aliases = {alias: slug for slug, club in clubs.items() for alias in club["aliases"]}
    if name not in aliases:
        raise ValueError(f"Unknown historical club: {name!r}")
    return aliases[name]


def normalize(matches: list[dict], clubs: dict) -> list[dict]:
    return [
        {**m, "home": resolve(m["home"], clubs), "away": resolve(m["away"], clubs)} for m in matches
    ]


def calculate_table(matches: list[dict], adjustments: dict | None = None) -> list[dict]:
    rows = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    for m in matches:
        for own, _other, gf, ga in (
            (m["home"], m["away"], m["home_goals"], m["away_goals"]),
            (m["away"], m["home"], m["away_goals"], m["home_goals"]),
        ):
            row = rows[own]
            row["played"] += 1
            row["goals_for"] += gf
            row["goals_against"] += ga
            row["wins" if gf > ga else "draws" if gf == ga else "losses"] += 1
    for slug, row in rows.items():
        row["goal_difference"] = row["goals_for"] - row["goals_against"]
        row["point_adjustment"] = (adjustments or {}).get(slug, 0)
        row["points"] = 3 * row["wins"] + row["draws"] + row["point_adjustment"]
        row["club_slug"] = slug
    ordered = sorted(
        rows.values(),
        key=lambda r: (-r["points"], -r["goal_difference"], -r["goals_for"], r["club_slug"]),
    )
    for i, row in enumerate(ordered, 1):
        row["position"] = i
    return ordered


def load_fjelstul(path: Path, clubs: dict) -> dict:
    result = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            year = int(row["season"])
            if row["tier"] == "1" and 1992 <= year <= 2023:
                result[str(year)].append(
                    {
                        "club_slug": resolve(row["team_name"], clubs),
                        **{
                            field: int(row[field])
                            for field in (*FIELDS, "position", "point_adjustment")
                        },
                    }
                )
    return dict(result)


def load_fjelstul_champions(path: Path, clubs: dict) -> dict:
    """Top-flight champions and runners-up before the Premier League, by Fjelstul team id."""
    # The team id, not the name, so former names ("The Wednesday") count for the club.
    by_id = {
        club["fjelstul_team_id"]: slug
        for slug, club in clubs.items()
        if club.get("fjelstul_team_id")
    }
    found = defaultdict(lambda: {"1": [], "2": []})
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["tier"] == "1" and int(row["season"]) < 1992 and row["position"] in ("1", "2"):
                slug = by_id.get(row["team_id"])
                team = {"slug": slug, "name": clubs[slug]["name"] if slug else row["team_name"]}
                found[row["season"]][row["position"]].append(team)
    early = {}
    for season, places in sorted(found.items()):
        if len(places["1"]) != 1 or len(places["2"]) != 1:
            raise ValueError(f"{season}: expected one champion and one runner-up")
        early[season] = {"champion": places["1"][0], "runner_up": places["2"][0]}
    return early


def verify_table(matches: list[dict], reference: list[dict]) -> None:
    actual = {
        r["club_slug"]: r
        for r in calculate_table(
            matches, {r["club_slug"]: r["point_adjustment"] for r in reference}
        )
    }
    if set(actual) != {r["club_slug"] for r in reference}:
        raise ValueError("Table club set differs from match data")
    for expected in reference:
        for field in FIELDS:
            if actual[expected["club_slug"]][field] != expected[field]:
                raise ValueError(
                    f"{matches[0]['season']} {expected['club_slug']} {field}: "
                    f"{actual[expected['club_slug']][field]} != {expected[field]}"
                )


CREDIT = (
    "Sources: match results from openfootball/england (CC0 1.0), "
    "https://github.com/openfootball/england; final tables through 2023/24 from "
    "the Fjelstul English Football Database, © 2024 Joshua C. Fjelstul, Ph.D., "
    "https://github.com/jfjelstul/englishfootball. Adapted: names normalized, "
    "tables converted to English summaries, team-season and head-to-head statistics computed. "
    "Historical documents are shared under CC-BY-SA 4.0: "
    "https://creativecommons.org/licenses/by-sa/4.0/legalcode."
)


def season_label(season: str) -> str:
    return f"{season}/{str(int(season) + 1)[2:]}"


def relegated(season: str, rows: list[dict]) -> list[dict]:
    # 1994/95 relegated four clubs during the reduction from 22 to 20.
    ordered = sorted(rows, key=lambda row: row["position"])
    return ordered[-(4 if season == "1994" else 3) :]


def table_stats(row: dict) -> str:
    return (
        f"P{row['played']} W{row['wins']} D{row['draws']} L{row['losses']} "
        f"GF{row['goals_for']} GA{row['goals_against']} "
        f"GD{row['goal_difference']:+} Pts{row['points']}"
        + (f"; point adjustment {row['point_adjustment']}" if row.get("point_adjustment") else "")
    )


def historical_document(clubs, doc_id, title, text, topic, season, slugs, origin, url) -> dict:
    return {
        "doc_id": doc_id,
        "title": title,
        "text": text + "\n## Sources and license\n" + CREDIT,
        "category": "historical",
        "origin": origin,
        "topic": topic,
        "season": season,
        "matchweek": None,
        "team_ids": sorted({clubs[s]["team_id"] for s in slugs if clubs[s]["team_id"] is not None}),
        "date": None,
        "fetched_at": None,
        "url": url,
    }


def make_documents(
    seasons: dict,
    tables: dict,
    clubs: dict,
    source_urls: dict,
    scorers: dict | None = None,
) -> list[dict]:
    documents, pairs = [], defaultdict(list)
    doc = partial(historical_document, clubs)

    def result(m):
        return (
            f"{m['date']} MW{m['matchweek']}: {clubs[m['home']]['name']} "
            f"{m['home_goals']}-{m['away_goals']} {clubs[m['away']]['name']}"
        )

    for season, matches in sorted(seasons.items()):
        rows = sorted(tables[season], key=lambda row: row["position"])
        title = f"Premier League {season}/{str(int(season) + 1)[2:]} final table"
        text = (
            f"Champions: {clubs[rows[0]['club_slug']]['name']}, {rows[0]['points']} points. "
            f"Runners-up: {clubs[rows[1]['club_slug']]['name']}, {rows[1]['points']} points.\n"
        )
        down = relegated(season, rows)
        text += "Relegated: " + ", ".join(clubs[r["club_slug"]]["name"] for r in down) + ".\n"
        for offset in range(0, len(rows), 5):
            text += f"## Table: positions {offset + 1}-{min(offset + 5, len(rows))}\n"
            text += (
                "\n".join(
                    f"{r['position']}. {clubs[r['club_slug']]['name']}: {table_stats(r)}"
                    for r in rows[offset : offset + 5]
                )
                + "\n"
            )
        biggest = max(matches, key=lambda m: abs(m["home_goals"] - m["away_goals"]))
        text += (
            f"## Season facts\nMatches: {len(matches)}. "
            f"Total goals: {sum(m['home_goals'] + m['away_goals'] for m in matches)}. "
            f"Biggest winning margin: {result(biggest)}.\n"
        )
        if scorers and season in scorers:
            source = scorers[season]
            text += "## Top scorers\n"
            for rank, player in enumerate(source["items"], 1):
                names = ", ".join(clubs[s]["name"] for s in player["clubs"])
                full = player.get("full_name")
                label = f"{player['player']} / {full}" if full else player["player"]
                text += f"{rank}. {label} ({names}): {player['goals']} goals.\n"
            text += f"Source: {source['name']}. {source['url']}\n"
        documents.append(
            doc(
                f"hist-season-{season}",
                title,
                text,
                "season_table",
                season,
                [r["club_slug"] for r in rows],
                "fjelstul" if int(season) <= 2023 else "openfootball",
                "https://github.com/jfjelstul/englishfootball"
                if int(season) <= 2023
                else source_urls[season],
            )
        )
        for row in rows:
            slug = row["club_slug"]
            own = sorted(
                [m for m in matches if slug in (m["home"], m["away"])], key=lambda m: m["date"]
            )
            title = f"{clubs[slug]['name']} — Premier League {season}/{str(int(season) + 1)[2:]}"
            text = f"Final position: {row['position']}. {table_stats(row)}.\n## Home and away\n"
            for side in ("home", "away"):
                side_rows = calculate_table([m for m in own if m[side] == slug])
                side_row = next(r for r in side_rows if r["club_slug"] == slug)
                text += f"{side.title()}: {table_stats(side_row)}.\n"
            # Keep results sections short enough for retrieval's heading-based chunker.
            for offset in range(0, len(own), 5):
                text += f"## Results {offset + 1}-{min(offset + 5, len(own))}\n"
                text += "\n".join(result(m) for m in own[offset : offset + 5]) + "\n"
            documents.append(
                doc(
                    f"hist-team-{season}-{slug}",
                    title,
                    text,
                    "team_season",
                    season,
                    [slug],
                    "openfootball",
                    source_urls[season],
                )
            )
        for match in matches:
            pairs[tuple(sorted((match["home"], match["away"])))].append(match)
    for (a, b), matches in sorted(pairs.items()):
        names = {s: clubs[s]["name"] for s in (a, b)}

        def summary(items, a=a, b=b, names=names):
            wins = {a: 0, b: 0}
            draws = 0
            for m in items:
                if m["home_goals"] == m["away_goals"]:
                    draws += 1
                else:
                    wins[m["home"] if m["home_goals"] > m["away_goals"] else m["away"]] += 1
            return (
                f"{len(items)} meetings: {names[a]} won {wins[a]}, "
                f"draws {draws}, {names[b]} won {wins[b]}."
            )

        title = f"{names[a]} vs {names[b]} — Premier League head-to-head"
        text = "Coverage: 1992/93 to 2025/26. " + summary(matches) + "\n"
        text += "## Home and away\n" + "\n".join(
            f"At {names[s]} home: {summary([m for m in matches if m['home'] == s])}" for s in (a, b)
        )
        text += "\n## Recent meetings\n" + "\n".join(
            result(m) for m in sorted(matches, key=lambda m: m["date"], reverse=True)[:6]
        )
        biggest_wins = []
        for s in (a, b):

            def margin(match, side=s):
                return (match["home_goals"] - match["away_goals"]) * (
                    1 if match["home"] == side else -1
                )

            won = [match for match in matches if margin(match) > 0]
            biggest_wins.append(
                result(max(won, key=margin))
                if won
                else f"No Premier League wins for {names[s]} against {names[b if s == a else a]}."
            )
        text += "\n## Biggest wins\n" + "\n".join(biggest_wins)
        documents.append(
            doc(
                f"hist-h2h-{a}-{b}",
                title,
                text,
                "head_to_head",
                None,
                [a, b],
                "openfootball",
                "https://github.com/openfootball/england",
            )
        )
    return documents


GOAL_TOKEN = re.compile(r"^(?:(.*?)\s+)?(\d+(?:\+\d+)?)'\s*(\(og\)|\(p\))?$")


def parse_goal_block(text: str, match: dict) -> list[dict]:
    """Parse credited sides, retaining own goals for validation but not player totals."""
    content = text.strip()[1:-1]
    parts = content.split(";")
    if len(parts) == 1:
        if match["home_goals"] and match["away_goals"]:
            raise ValueError("Scorer block needs a home/away separator")
        sides = [("home" if match["home_goals"] else "away", parts[0])]
    elif len(parts) == 2:
        sides = list(zip(("home", "away"), parts, strict=True))
    else:
        raise ValueError("Too many scorer-side separators")
    goals = []
    for side, part in sides:
        player = None
        for token in part.split(","):
            token = token.strip()
            if not token:
                continue
            parsed = GOAL_TOKEN.fullmatch(token)
            if not parsed:
                raise ValueError(f"Unrecognized goal token: {token}")
            if parsed[1]:
                player = " ".join(parsed[1].split())
            if not player:
                raise ValueError("Goal minute without a player name")
            goals.append(
                {
                    "player": player,
                    "minute": parsed[2],
                    "side": side,
                    "own_goal": parsed[3] == "(og)",
                    "penalty": parsed[3] == "(p)",
                }
            )
    for side in ("home", "away"):
        if sum(g["side"] == side for g in goals) != match[f"{side}_goals"]:
            raise ValueError("Scorer block does not reconcile to the final score")
    return goals


def season_scorers(matches: list[dict]) -> list[dict]:
    import unicodedata

    players = {}
    for match in matches:
        if match["home_goals"] + match["away_goals"] and "goals" not in match:
            raise ValueError("Incomplete scorer coverage; refusing to estimate totals")
        for goal in match.get("goals", []):
            if goal["own_goal"]:
                continue
            key = unicodedata.normalize("NFKC", goal["player"]).casefold()
            row = players.setdefault(
                key, {"player": goal["player"].title(), "goals": 0, "clubs": set()}
            )
            row["goals"] += 1
            row["clubs"].add(match[goal["side"]])
    return [
        {**row, "clubs": sorted(row["clubs"])}
        for row in sorted(players.values(), key=lambda r: (-r["goals"], r["player"]))
    ]


def load_scorer_sources(
    raw: Path, clubs: dict, seasons: dict, source_urls: dict
) -> tuple[dict, dict]:
    """Never publish a scorer source that disagrees with the reviewed official podium."""
    import hashlib
    import json

    reference = json.loads(
        (Path(__file__).parents[1] / "data/scorer_reference.json").read_text(encoding="utf-8")
    )
    sources, validation = {}, {}
    for year in ("2022", "2023", "2024", "2025"):
        if year == "2025":
            items = season_scorers(seasons[year])
            source = {"name": "openfootball", "url": source_urls[year], "items": items}
        else:
            path = raw / f"scorers/{year}.json"
            if not path.exists():
                validation[year] = {"status": "missing"}
                continue
            meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
            if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
                raise ValueError("Historical scorer cache checksum mismatch")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("errors") or not payload.get("response"):
                raise ValueError("Invalid historical scorer cache")
            items = []
            for player in payload["response"]:
                stat = player["statistics"][0]
                if stat["league"]["id"] != 39 or str(stat["league"]["season"]) != year:
                    raise ValueError("Wrong scorer league/season")
                full_name = " ".join(
                    filter(
                        None, (player["player"].get("firstname"), player["player"].get("lastname"))
                    )
                )
                items.append(
                    {
                        "player": player["player"]["name"],
                        "full_name": full_name,
                        "goals": stat["goals"]["total"],
                        "clubs": [resolve(stat["team"]["name"], clubs)],
                    }
                )
            source = {
                "name": "API-Football",
                "url": "https://www.api-football.com/documentation-v3#tag/Players/operation/get-players-topscorers",
                "items": items,
            }
        observed = sorted(items, key=lambda item: -item["goals"])[:3]
        expected = reference[year]["top3"]
        matches = len(observed) == 3 and all(
            name.casefold() in got["player"].casefold() and goals == got["goals"]
            for (name, goals), got in zip(expected, observed, strict=True)
        )
        validation[year] = {
            "status": "accepted" if matches else "rejected",
            "official_url": reference[year]["url"],
            "check_scope": "top three only; not a full-player official validation",
            "observed_top3": [{"player": r["player"], "goals": r["goals"]} for r in observed],
        }
        if matches:
            sources[year] = source
    return sources, validation
