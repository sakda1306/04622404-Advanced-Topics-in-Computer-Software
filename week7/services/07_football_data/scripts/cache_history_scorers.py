"""Cache actual API-Football historical top scorers; at most three requests."""

# ruff: noqa: E402
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.history import resolve
from scripts.env_file import repo_env_file


async def main():
    settings = Settings(_env_file=repo_env_file(ROOT))
    raw = ROOT / "data/raw/history/scorers"
    raw.mkdir(parents=True, exist_ok=True)
    clubs = json.loads((ROOT / "data/historical_clubs.json").read_text(encoding="utf-8"))
    async with httpx.AsyncClient(timeout=30) as client:
        for year in (2022, 2023, 2024):
            path = raw / f"{year}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
            else:
                response = await client.get(
                    settings.api_football_base_url + "/players/topscorers",
                    params={"league": 39, "season": year},
                    headers={"x-apisports-key": settings.api_football_key},
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("errors") or not payload.get("response"):
                    raise ValueError(f"Top scorers unavailable for {year}; refusing empty cache")
                if payload.get("paging", {}).get("total", 1) != 1:
                    raise ValueError("Unexpected paginated top-scorer response")
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                evidence = {
                    "source": "API-Football",
                    "endpoint": "/players/topscorers",
                    "league": 39,
                    "season": year,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                (raw / f"{year}.meta.json").write_text(
                    json.dumps(evidence, indent=2), encoding="utf-8"
                )
            for player in payload["response"]:
                stats = player["statistics"][0]
                if stats["league"]["id"] != 39 or stats["league"]["season"] != year:
                    raise ValueError("Wrong scorer league/season")
                resolve(stats["team"]["name"], clubs)
            print(
                year,
                "cached players:",
                len(payload["response"]),
                "top:",
                [
                    (p["player"]["name"], p["statistics"][0]["goals"]["total"])
                    for p in payload["response"][:3]
                ],
            )


if __name__ == "__main__":
    asyncio.run(main())
