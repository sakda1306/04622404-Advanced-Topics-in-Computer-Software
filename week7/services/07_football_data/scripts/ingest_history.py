"""One-shot history preparation: download pinned sources, verify, persist, optionally index."""

# Standalone entry points add the service root before importing app modules.
# ruff: noqa: E402

import argparse
import asyncio
import csv
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.db import Base, HistoricalMatch, HistoricalStanding, make_database
from app.football import current_season
from app.history import (
    calculate_table,
    load_fjelstul,
    load_fjelstul_champions,
    load_scorer_sources,
    make_documents,
    normalize,
    parse_season,
    resolve,
    verify_table,
)
from app.history_records import make_record_documents
from app.service import FootballService
from scripts.download_history import main as download
from scripts.env_file import repo_env_file

PINNED = {
    "openfootball": "b17e8f01707d83d2ce1790c14d4a5eeb35987825",
    "fjelstul": "ff3c37698065476e1852243685da6b756a580b9f",
}


def build_dataset():
    raw = ROOT / "data/raw/history"
    manifest = json.loads((raw / "manifest.json").read_text(encoding="utf-8"))
    for source, sha in PINNED.items():
        if manifest[source]["commit"] != sha:
            raise ValueError(f"Unapproved source commit: {source}")
        for item in manifest[source]["files"]:
            if (
                hashlib.sha256((raw / source / item["local"]).read_bytes()).hexdigest()
                != item["sha256"]
            ):
                raise ValueError(f"Source file changed: {source}/{item['local']}")
    clubs = json.loads((ROOT / "data/historical_clubs.json").read_text(encoding="utf-8"))
    aliases = [alias for club in clubs.values() for alias in club["aliases"]]
    if len(aliases) != len(set(aliases)):
        raise ValueError("Ambiguous club alias mapping")
    # Validate team identities independently against Fjelstul's teams.csv.
    with (raw / "fjelstul/teams.csv").open(encoding="utf-8-sig", newline="") as handle:
        for team in csv.DictReader(handle):
            if team["team_name"] in aliases:
                slug = resolve(team["team_name"], clubs)
                clubs[slug]["fjelstul_team_id"] = team["team_id"]
    if any("fjelstul_team_id" not in club for club in clubs.values()):
        raise ValueError("Missing Fjelstul teams.csv identity")
    seasons = {}
    for year in range(1992, 2026):
        if year >= int(current_season()):
            raise ValueError("Refusing current/future season in history")
        seasons[str(year)] = normalize(
            parse_season((raw / f"openfootball/{year}.txt").read_text(encoding="utf-8-sig"), year),
            clubs,
        )
    tables = load_fjelstul(raw / "fjelstul/standings.csv", clubs)
    if len(tables) != 32:
        raise ValueError("Expected 32 Fjelstul overlapping seasons")
    for year, rows in tables.items():
        verify_table(seasons[year], rows)
    deductions = json.loads((ROOT / "data/point_deductions.json").read_text(encoding="utf-8"))
    for year in ("2024", "2025"):
        if not deductions[year]["official_table_verified"]:
            raise ValueError(f"Official final table not reviewed: {year}")
        tables[year] = calculate_table(seasons[year], deductions[year]["adjustments"])
    source_urls = {
        Path(item["local"]).stem: item["url"]
        for item in manifest["openfootball"]["files"]
        if item["local"].endswith(".txt")
    }
    scorers, _validation = load_scorer_sources(raw, clubs, seasons, source_urls)
    documents = make_documents(seasons, tables, clubs, source_urls, scorers)
    early = load_fjelstul_champions(raw / "fjelstul/standings.csv", clubs)
    if len(early) != 93:
        raise ValueError("Expected 93 First Division seasons before 1992")
    documents += make_record_documents(tables, clubs, early)
    if len({d["doc_id"] for d in documents}) != len(documents):
        raise ValueError("Duplicate historical document ID")
    return seasons, tables, clubs, documents


async def persist(engine, seasons, tables):
    insert = sqlite_insert if engine.dialect.name == "sqlite" else pg_insert
    match_rows = [
        {
            "match_id": f"hist-match-{year}-{m['home']}-{m['away']}",
            "season": year,
            "home_slug": m["home"],
            "away_slug": m["away"],
            "payload": m,
        }
        for year, matches in seasons.items()
        for m in matches
    ]
    standing_rows = [
        {"season": year, "club_slug": row["club_slug"], "payload": row}
        for year, rows in tables.items()
        for row in rows
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        for model, rows, keys in (
            (HistoricalMatch, match_rows, ["match_id"]),
            (HistoricalStanding, standing_rows, ["season", "club_slug"]),
        ):
            for offset in range(0, len(rows), 500):
                statement = insert(model).values(rows[offset : offset + 500])
                statement = statement.on_conflict_do_update(
                    index_elements=keys,
                    set_={
                        column.name: getattr(statement.excluded, column.name)
                        for column in model.__table__.columns
                        if column.name not in keys
                    },
                )
                await connection.execute(statement)


async def main(args):
    if not args.offline:
        await download()
    seasons, tables, clubs, documents = build_dataset()
    generated = ROOT / "data/raw/history/generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "documents.json").write_text(
        json.dumps(documents, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (generated / "clubs.json").write_text(
        json.dumps(clubs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source_urls = {
        year: next(d["url"] for d in documents if d["doc_id"] == f"hist-team-{year}-arsenal")
        for year in seasons
        if any(d["doc_id"] == f"hist-team-{year}-arsenal" for d in documents)
    }
    _scorers, validation = load_scorer_sources(
        ROOT / "data/raw/history", clubs, seasons, source_urls
    )
    (generated / "scorer-validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "seasons": len(seasons),
        "matches": sum(map(len, seasons.values())),
        "clubs": len(clubs),
        "team_seasons": sum(map(len, tables.values())),
        "documents": len(documents),
        "by_topic": {
            topic: sum(d["topic"] == topic for d in documents)
            for topic in (
                "season_table",
                "team_season",
                "head_to_head",
                "club_record",
                "league_records",
            )
        },
        "source_commits": PINNED,
        "scorer_validation": {year: row["status"] for year, row in validation.items()},
    }
    (generated / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    settings = Settings(_env_file=repo_env_file(ROOT), database_url=args.database_url)
    if args.index and not settings.historical_index_enabled:
        raise ValueError(
            "Historical CONTRACT/05 integration is not enabled. Agree contract first, "
            "then set HISTORICAL_INDEX_ENABLED=true."
        )
    engine, sessions = make_database(settings.database_url)
    try:
        await persist(engine, seasons, tables)
        if args.index:
            async with httpx.AsyncClient(timeout=30) as client:
                service = FootballService(settings, sessions, client)
                async with sessions() as db:
                    await service._queue_documents(db, documents, str(uuid4()))
                    await db.commit()
                await service.reconcile_index()
    finally:
        await engine.dispose()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Use downloaded inputs; verify manifest checksums"
    )
    parser.add_argument(
        "--database-url",
        default="sqlite+aiosqlite:///./history_local.db",
        help="Dedicated local DB by default; explicitly select production DB",
    )
    parser.add_argument(
        "--index", action="store_true", help="Requires agreed CONTRACT and HISTORICAL_INDEX_ENABLED"
    )
    asyncio.run(main(parser.parse_args()))
