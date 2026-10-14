"""Isolated 2024/25 details demo; never writes current-season DB/index."""

# Standalone entry point adds service root before app imports.
# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.api_football import enriched_match, match_api_fixture
from app.config import Settings
from app.football import bangkok_iso
from app.history import resolve
from scripts.env_file import repo_env_file

RAW = ROOT / "data/raw/provider-smoke"


def build_demo():
    def cached(name):
        payload = json.loads((RAW / f"api-football-2024-{name}.json").read_text(encoding="utf-8"))
        if payload.get("errors"):
            raise ValueError("Cached provider response contains an error")
        return payload["response"]

    fixture = cached("fixture")[0]
    if fixture["league"]["season"] != 2024 or fixture["league"]["id"] != 39:
        raise ValueError("Demo fixture is not Premier League 2024/25")
    clubs = json.loads((ROOT / "data/historical_clubs.json").read_text(encoding="utf-8"))
    teams = {
        side: clubs[resolve(fixture["teams"][side]["name"], clubs)] for side in ("home", "away")
    }
    fetched_at = datetime.now(UTC).isoformat()
    match = {
        "match_id": str(uuid5(NAMESPACE_URL, "api-football-demo:" + str(fixture["fixture"]["id"]))),
        "external_ids": {"football_data": None, "api_football": fixture["fixture"]["id"]},
        "season": "2024",
        "matchweek": int(fixture["league"]["round"].rsplit(" ", 1)[-1]),
        "kickoff": bangkok_iso(fixture["fixture"]["date"]),
        "status": "FINISHED",
        **{
            side: {"team_id": teams[side]["team_id"], "name": teams[side]["name"]}
            for side in ("home", "away")
        },
        "score": {**fixture["goals"], "half_time": fixture["score"]["halftime"]},
        "events": [],
        "lineups": None,
        "statistics": None,
        "fetched_at": fetched_at,
        "detail_source": "none",
    }
    if match_api_fixture(match, [fixture]) is None:
        raise ValueError("Fixture identity mismatch")
    result = enriched_match(
        match, fixture, cached("events"), cached("lineups"), cached("statistics"), fetched_at
    )
    result["demo_only"] = True
    return result


async def main(offline):
    if not offline:
        settings = Settings(_env_file=repo_env_file(ROOT))
        # One request; remaining event/lineup/statistic inputs came from check_providers.
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                settings.api_football_base_url + "/fixtures",
                params={"id": 1208399},
                headers={"x-apisports-key": settings.api_football_key},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors") or len(payload.get("response", [])) != 1:
                raise ValueError("Provider could not return the selected demo fixture")
            (RAW / "api-football-2024-fixture.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
    demo = build_demo()
    (RAW / "demo-match-2024.json").write_text(
        json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "season": demo["season"],
                "fixture_id": demo["external_ids"]["api_football"],
                "home": demo["home"]["name"],
                "away": demo["away"]["name"],
                "score": demo["score"],
                "events": len(demo["events"]),
                "lineups": len(demo["lineups"]),
                "statistics": len(demo["statistics"]),
                "demo_only": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    asyncio.run(main(parser.parse_args().offline))
