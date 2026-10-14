"""Current head coaches from Wikidata P286 (CONTRACT v1.16): football-data.org leaves them empty."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import httpx

CLUBS_FILE = Path(__file__).resolve().parents[1] / "data" / "wikidata_clubs.json"
SPARQL_URL = "https://query.wikidata.org/sparql"
REPO_URL = "https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D-II"
TIMEOUT_SECONDS = 20.0
QID = re.compile(r"^Q\d+$")
# An "unknown value" date comes back as a genid URI, not as a date.
ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class CoachFetchError(Exception):
    """Wikidata did not answer usably; the previous coach documents stay."""


def load_club_qids(path: Path = CLUBS_FILE) -> dict[int, str]:
    return {
        int(team_id): qid for team_id, qid in json.loads(path.read_text(encoding="utf-8")).items()
    }


def coach_query(qids: list[str]) -> str:
    clubs = " ".join(f"wd:{qid}" for qid in qids if QID.match(qid))
    return (
        "SELECT ?club ?coachLabel ?rank ?start ?end WHERE { "
        f"VALUES ?club {{ {clubs} }} "
        "?club p:P286 ?statement. ?statement ps:P286 ?coach; wikibase:rank ?rank. "
        "OPTIONAL { ?statement pq:P580 ?start } OPTIONAL { ?statement pq:P582 ?end } "
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
    )


def _value(row: dict, key: str) -> str | None:
    cell = row.get(key)
    return cell.get("value") if isinstance(cell, dict) else None


def parse_coaches(payload: dict) -> dict[str, list[dict]]:
    try:
        rows = payload["results"]["bindings"]
    except (KeyError, TypeError) as exc:
        raise CoachFetchError("no bindings in the SPARQL answer") from exc
    if not isinstance(rows, list):
        raise CoachFetchError("bindings is not a list")
    coaches: dict[str, list[dict]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        club, name, rank = _value(row, "club"), _value(row, "coachLabel"), _value(row, "rank")
        # Without an English label Wikidata returns the QID itself; that is no name to show.
        if not club or not name or not rank or QID.match(name):
            continue
        start, end = _value(row, "start"), _value(row, "end")
        coaches.setdefault(club.rsplit("/", 1)[-1], []).append(
            {
                "name": name,
                "rank": rank.rsplit("#", 1)[-1].removesuffix("Rank").lower(),
                "start": start[:10] if start and ISO_DAY.match(start) else None,
                # An unknown end date still means the job ended.
                "end": (end[:10] if ISO_DAY.match(end) else "unknown") if end else None,
            }
        )
    if not coaches:
        # Nothing usable: keep the previous documents instead of writing "no coach" for every club.
        raise CoachFetchError("no usable head coach statement")
    return coaches


def current_coach(statements: list[dict]) -> dict | None:
    open_ = [s for s in statements if s["end"] is None and s["rank"] != "deprecated"]
    preferred = [s for s in open_ if s["rank"] == "preferred"]
    candidates = preferred or open_
    if not candidates:
        return None
    return max(candidates, key=lambda s: s["start"] or "")


def _long_date(iso: str) -> str:
    day = date.fromisoformat(iso)
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def coach_document(
    team_id: int, team_name: str, qid: str, coach: dict | None, season: str, fetched_at: str
) -> dict:
    checked = fetched_at[:10]
    if coach is None:
        text = f"Wikidata lists no current head coach for {team_name} (checked {checked})."
    else:
        since = f", since {_long_date(coach['start'])}" if coach["start"] else ""
        text = (
            f"Who is the head coach of {team_name}? {coach['name']}.\n"
            f"{team_name} head coach (manager): {coach['name']}{since}.\n"
            f"Source: Wikidata ({qid}), checked {checked}."
        )
    return {
        "doc_id": f"coach-{season}-team-{team_id}",
        "title": f"{team_name} head coach",
        "text": text,
        "category": "player",
        "origin": "wikidata",
        "topic": "head_coach",
        "season": season,
        "matchweek": None,
        "team_ids": [team_id],
        "date": checked,
        "fetched_at": fetched_at,
        "url": f"https://www.wikidata.org/wiki/{qid}",
    }


async def fetch_coaches(
    http: httpx.AsyncClient, qids: list[str], version: str
) -> dict[str, list[dict]]:
    qids = [qid for qid in qids if QID.match(qid)]
    if not qids:
        return {}
    headers = {
        "User-Agent": f"football-assistant-course-project/{version} ({REPO_URL})",
        "Accept": "application/sparql-results+json",
    }
    try:
        response = await http.get(
            SPARQL_URL,
            params={"query": coach_query(qids)},
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CoachFetchError(str(exc)[:200]) from exc
    return parse_coaches(payload)
