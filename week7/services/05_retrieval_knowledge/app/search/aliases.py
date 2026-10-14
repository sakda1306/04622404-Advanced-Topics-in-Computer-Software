"""Team nicknames -> official names, added to the BM25 query (week5 #1).

Matching rules, so ordinary words are not mistaken for teams:
- English aliases match whole words only ("spurs" but not "spursy")
- Thai aliases match whole words from the tokenizer ("ผี" but not inside "ผีเสื้อ")
- longest alias first; a matched span cannot be matched again by a shorter alias
Only the query text is expanded; team_ids filters stay the router's decision.

Nicknames come from 07 `GET /football/teams`, the same source the router uses. A
background task refreshes them; searches read whatever set is current and never wait
for 07. Until 07 answers, or when it answers with nothing usable, the bundled file is used.
07's teams are merged into the bundled file by team_id, not swapped in for it: a team 07
has no nicknames for keeps the bundled ones.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import get_logger
from app.search.tokenize import tokenize

log = get_logger(__name__)

_THAI = re.compile(r"[ก-๙]")


@dataclass(frozen=True, slots=True)
class TeamAliases:
    team_id: int
    names: tuple[str, ...]
    aliases: tuple[str, ...]


def parse_teams(data: Mapping[str, Any]) -> list[TeamAliases]:
    """Read the `GET /football/teams` shape (CONTRACT §7)."""
    teams: list[TeamAliases] = []
    for team in data.get("teams", []):
        names = tuple(dict.fromkeys(n for n in (team.get("short_name"), team.get("name")) if n))
        aliases = tuple(a for a in team.get("aliases", []) if isinstance(a, str) and a.strip())
        teams.append(TeamAliases(int(team["team_id"]), names, aliases))
    return teams


def merge_teams(base: Sequence[TeamAliases], feed: Sequence[TeamAliases]) -> list[TeamAliases]:
    """Teams of both, by team_id: the feed's names win, nicknames from both are kept."""
    merged = {team.team_id: team for team in base}
    for team in feed:
        known = merged.get(team.team_id)
        if known is None:
            merged[team.team_id] = team
            continue
        merged[team.team_id] = TeamAliases(
            team.team_id,
            team.names or known.names,
            tuple(dict.fromkeys((*team.aliases, *known.aliases))),
        )
    return list(merged.values())


class AliasIndex:
    def __init__(self, teams: Sequence[TeamAliases]) -> None:
        self.teams = tuple(teams)
        english: list[tuple[re.Pattern[str], TeamAliases]] = []
        thai: list[tuple[tuple[str, ...], TeamAliases]] = []
        for team in teams:
            for alias in team.aliases:
                lowered = alias.strip().lower()
                if _THAI.search(lowered):
                    tokens = tuple(tokenize(lowered))
                    if tokens:
                        thai.append((tokens, team))
                else:
                    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])")
                    english.append((pattern, team))
        self._english = sorted(english, key=lambda item: len(item[0].pattern), reverse=True)
        self._thai = sorted(thai, key=lambda item: len(item[0]), reverse=True)
        self.team_count = len(teams)

    def expand(self, *texts: str | None) -> list[str]:
        """Official names of every team mentioned by nickname in the texts."""
        found: list[TeamAliases] = []
        for text in texts:
            if not text:
                continue
            lowered = text.lower()
            for pattern, team in self._english:
                if pattern.search(lowered):
                    found.append(team)
                    lowered = pattern.sub(" ", lowered)
            tokens = tokenize(lowered)
            used = [False] * len(tokens)
            for alias_tokens, team in self._thai:
                size = len(alias_tokens)
                for start in range(len(tokens) - size + 1):
                    span = range(start, start + size)
                    if tuple(tokens[start : start + size]) == alias_tokens and not any(
                        used[i] for i in span
                    ):
                        found.append(team)
                        for i in span:
                            used[i] = True
        names: list[str] = []
        for team in found:
            for name in team.names:
                if name not in names:
                    names.append(name)
        return names


def load_alias_file(path: str) -> AliasIndex:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("aliases_unavailable", path=path, error_type=type(exc).__name__)
        return AliasIndex([])
    return AliasIndex(parse_teams(data))


class AliasProvider:
    """The alias set in use; replaced whole, so a search sees the old set or the new one."""

    def __init__(self, fallback: AliasIndex) -> None:
        self.fallback = fallback
        self._current = fallback

    @property
    def current(self) -> AliasIndex:
        return self._current

    def expand(self, *texts: str | None) -> list[str]:
        return self._current.expand(*texts)

    def replace(self, index: AliasIndex) -> None:
        self._current = index


async def refresh_aliases(provider: AliasProvider, client: httpx.AsyncClient) -> bool:
    """Load the aliases from 07; False, keeping the current set, when that fails."""
    try:
        response = await client.get("/football/teams")
        response.raise_for_status()
        teams = parse_teams(response.json())
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        log.warning("aliases_fetch_failed", error_type=type(exc).__name__)
        return False
    if not any(team.aliases for team in teams):
        # An empty answer would silently switch nickname search off.
        log.warning("aliases_fetch_empty", teams=len(teams))
        return False
    merged = merge_teams(provider.fallback.teams, teams)
    # Thai aliases go through the tokenizer: CPU work, kept off the event loop.
    provider.replace(await asyncio.to_thread(AliasIndex, merged))
    log.info("aliases_refreshed", teams=len(teams))
    return True


async def keep_aliases_fresh(
    provider: AliasProvider, client: httpx.AsyncClient, *, every: float, retry_after: float
) -> None:
    """Refresh every `every` seconds; after a failure, try again after `retry_after`."""
    while True:
        try:
            ok = await refresh_aliases(provider, client)
        except Exception:
            # A crash must not end the task: nicknames would stop refreshing for good.
            log.exception("aliases_refresh_crashed")
            ok = False
        await asyncio.sleep(every if ok else retry_after)
