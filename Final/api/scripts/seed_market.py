"""Seed the shared job cache: one Apify run per role (PRD FR-22a). Each run costs credit.

Usage, from api/ or inside the api container:
    python -m scripts.seed_market --all --dry-run         # what would run, and its cost
    python -m scripts.seed_market --role data-analyst     # one role
    python -m scripts.seed_market --all                   # every role without fresh data

A role fetched within CACHE_MAX_AGE_DAYS is skipped, so a second run does not pay twice.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.clock import utcnow
from app.core.config import Settings
from app.domain import market
from app.domain.matching.roles import load_catalogue
from app.domain.matching.skills import load_taxonomy
from app.infra.db import create_engine, create_session_factory
from app.infra.models import RoleCache
from app.providers.apify_jobthai import ApifyJobThaiProvider
from app.services import market_service

COST_USD_PER_RESULT = 0.001  # the actor's price on 3 Nov 2026
COST_USD_PER_START = 0.00005


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    catalogue = load_catalogue(settings.data_dir)
    searches = market.load_role_search(settings.data_dir)
    taxonomy = load_taxonomy(settings.data_dir)
    if args.role:
        unknown = sorted(set(args.role) - {role.role_id for role in catalogue})
        if unknown:
            print(f"unknown role ids: {unknown}", file=sys.stderr)
            return 2
    roles = [role for role in catalogue if args.all or role.role_id in args.role]

    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    failed = 0
    try:
        async with sessions() as db:
            now = utcnow()
            todo = [
                role
                for role in roles
                if args.force
                or not market_service.is_fresh(await db.get(RoleCache, role.role_id), settings, now)
            ]
            most = market_service.POSTINGS_PER_ROLE * COST_USD_PER_RESULT + COST_USD_PER_START
            print(f"{len(todo)} of {len(roles)} roles to fetch, at most ${most * len(todo):.2f}")
            if args.dry_run:
                for role in todo:
                    print(f"  {role.role_id}: {searches[role.role_id].keyword}")
                return 0
            provider = ApifyJobThaiProvider(settings.apify_token, settings.apify_jobthai_actor)
            for role in todo:
                result = await market_service.refresh_role(
                    db, provider, role, searches=searches, taxonomy=taxonomy
                )
                failed += not result.ok
                outcome = (
                    f"kept {result.kept} of {result.fetched}, "
                    f"not Bangkok {result.not_bangkok}, not the role {result.not_the_role}, "
                    f"levels {result.levels}"
                    if result.ok
                    else result.error
                )
                print(f"  {role.role_id}: {outcome}", flush=True)
    finally:
        await engine.dispose()
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="every role in data/roles.json")
    which.add_argument("--role", action="append", default=[], help="a role id; can repeat")
    parser.add_argument("--dry-run", action="store_true", help="make no Apify call")
    parser.add_argument("--force", action="store_true", help="fetch fresh roles too")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
