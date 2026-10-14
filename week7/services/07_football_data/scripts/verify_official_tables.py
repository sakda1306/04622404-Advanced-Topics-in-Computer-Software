"""Compare the two latest historical seasons with the public official PL table."""

# Standalone entry points add the service root before importing app modules.
# ruff: noqa: E402

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.history import calculate_table, normalize, parse_season, resolve


async def main():
    clubs = json.loads((ROOT / "data/historical_clubs.json").read_text(encoding="utf-8"))
    async with httpx.AsyncClient(timeout=30) as client:
        for year in (2024, 2025):
            url = f"https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v5/competitions/8/seasons/{year}/standings"
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
            if payload.get("matchweek") != 38:
                raise ValueError("Official table is not final matchweek 38")
            entries = payload["tables"][0]["entries"]
            matches = normalize(
                parse_season(
                    (ROOT / f"data/raw/history/openfootball/{year}.txt").read_text(
                        encoding="utf-8-sig"
                    ),
                    year,
                ),
                clubs,
            )
            rows = {r["club_slug"]: r for r in calculate_table(matches)}
            if len(entries) != 20:
                raise ValueError("Official table does not contain 20 clubs")
            for entry in entries:
                slug = resolve(entry["team"]["name"], clubs)
                official = entry["overall"]
                mapping = {
                    "played": "played",
                    "wins": "won",
                    "draws": "drawn",
                    "losses": "lost",
                    "goals_for": "goalsFor",
                    "goals_against": "goalsAgainst",
                    "points": "points",
                    "position": "position",
                }
                for local, remote in mapping.items():
                    if rows[slug][local] != official[remote]:
                        raise ValueError(
                            f"{year} {slug} {local}: {rows[slug][local]} != {official[remote]}"
                        )
            target = ROOT / f"data/raw/history/official-{year}.json"
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(
                f"{year}: all 20 clubs, positions, W/D/L, goals and points match "
                "official PL final table; no point deductions required"
            )


if __name__ == "__main__":
    asyncio.run(main())
