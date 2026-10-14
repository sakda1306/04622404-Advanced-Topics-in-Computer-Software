"""Low-quota provider smoke test. Credentials only come from ignored root .env."""

# Standalone entry points add the service root before importing app modules.
# ruff: noqa: E402

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.football import current_season
from scripts.env_file import repo_env_file


async def main():
    settings = Settings(_env_file=repo_env_file(ROOT))
    output = ROOT / "data" / "raw" / "provider-smoke"
    output.mkdir(parents=True, exist_ok=True)
    summary = {"tested_at": datetime.now(UTC).isoformat(), "football_data": {}, "api_football": {}}
    async with httpx.AsyncClient(timeout=60) as client:
        for endpoint in ("teams", "matches", "standings", "scorers"):
            response = await client.get(
                settings.football_data_base_url + "/competitions/PL/" + endpoint,
                headers={"X-Auth-Token": settings.football_data_api_key},
            )
            payload = response.json()
            ok = response.is_success and "error" not in payload and "errorCode" not in payload
            summary["football_data"][endpoint] = {
                "status": response.status_code,
                "ok": ok,
                "count": payload.get("count", len(payload.get(endpoint, []))),
            }
            if ok:
                (output / f"football-data-{endpoint}.json").write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )

        async def api(endpoint, params=None):
            response = await client.get(
                settings.api_football_base_url + "/" + endpoint,
                params=params,
                headers={"x-apisports-key": settings.api_football_key},
            )
            payload = response.json()
            return response, payload

        response, payload = await api("status")
        summary["api_football"]["status"] = {
            "status": response.status_code,
            "errors": payload.get("errors"),
            "subscription": payload.get("response", {}).get("subscription"),
            "requests": payload.get("response", {}).get("requests"),
        }
        for year in (int(current_season()), int(current_season()) - 1, 2024):
            if str(year) in summary["api_football"]:
                continue
            response, payload = await api(
                "fixtures", {"league": 39, "season": year, "status": "FT"}
            )
            summary["api_football"][str(year)] = {
                "status": response.status_code,
                "errors": payload.get("errors"),
                "results": payload.get("results"),
            }
            fixtures = payload.get("response") or []
            if not payload.get("errors") and fixtures:
                fixture = fixtures[-1]["fixture"]["id"]
                for endpoint in ("events", "lineups", "statistics"):
                    response, details = await api("fixtures/" + endpoint, {"fixture": fixture})
                    summary["api_football"][str(year)][endpoint] = {
                        "status": response.status_code,
                        "errors": details.get("errors"),
                        "results": details.get("results"),
                    }
                    (output / f"api-football-{year}-{endpoint}.json").write_text(
                        json.dumps(details, ensure_ascii=False), encoding="utf-8"
                    )
                summary["api_football"][str(year)]["fixture_id"] = fixture
                break
    # Sanitize all diagnostics even if a provider echoes a token in an error.
    rendered = json.dumps(summary, indent=2, ensure_ascii=False)
    for secret in (settings.football_data_api_key, settings.api_football_key):
        if secret:
            rendered = rendered.replace(secret, "[REDACTED]")
    (output / "summary.json").write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    asyncio.run(main())
