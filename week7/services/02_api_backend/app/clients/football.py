"""Calls to 07 football-data (CONTRACT.md §7) and 05 retrieval index admin (§6)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from app.clients.service_client import ServiceClient
from app.core.clock import bangkok_now, season_for
from app.core.logging import get_logger
from app.infra.store import Store

log = get_logger(__name__)

STATUS_CACHE_KEY = "cache:football:status"
# After 07 fails, chats skip the status call for this long instead of waiting on it each time.
STATUS_RETRY_SECONDS = 30.0
PREDICTION_CACHE_SECONDS = 300


class FootballDataClient:
    def __init__(
        self,
        client: ServiceClient,
        *,
        store: Store,
        status_ttl_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._store = store
        self._status_ttl = status_ttl_seconds
        self._clock = clock
        self._status_down_until = 0.0

    # -- read ------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        data: dict[str, Any] = await self._client.get("/football/status")
        await self._store.set_json(STATUS_CACHE_KEY, data, self._status_ttl)
        return data

    async def cached_status(self) -> dict[str, Any] | None:
        """Status for the router context: cached 5 minutes, None when 07 is down."""
        cached = await self._store.get_json(STATUS_CACHE_KEY)
        if cached is not None:
            return dict(cached)
        if self._clock() < self._status_down_until:
            return None
        try:
            return await self.status()
        except Exception as exc:  # the chat must not fail because 07 is down
            log.warning("football_status_unavailable", error_type=type(exc).__name__)
            self._status_down_until = self._clock() + STATUS_RETRY_SECONDS
            return None

    async def standings(self, season: str | None) -> Any:
        return await self._client.get("/football/standings", season=season)

    async def fixtures(self, **filters: Any) -> Any:
        return await self._client.get("/football/fixtures", **filters)

    async def match(self, match_id: str) -> Any:
        return await self._client.get(f"/football/matches/{match_id}")

    async def _cached(self, key: str, path: str, **params: Any) -> Any:
        cached = await self._store.get_json(key)
        if cached is not None:
            return cached
        data = await self._client.get(path, **params)
        # A stale snapshot means 07 could not reach 04; ask again next time so recovery shows.
        if not (isinstance(data, dict) and data.get("stale") is True):
            await self._store.set_json(key, data, PREDICTION_CACHE_SECONDS)
        return data

    async def prediction(self, home_team_id: int, away_team_id: int) -> Any:
        return await self._cached(
            f"cache:football:predict:{home_team_id}:{away_team_id}",
            "/football/predict",
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )

    async def simulation(self, season: str | None) -> Any:
        return await self._cached(
            f"cache:football:simulation:{season or 'current'}",
            "/football/simulation",
            season=season,
        )

    async def published_report(self, season: str | None, matchweek: int | None) -> Any:
        return await self._client.get(
            "/football/reports/weekly", season=season, matchweek=matchweek
        )

    async def jobs(self, limit: int = 20) -> Any:
        return await self._client.get("/jobs", limit=limit)

    async def job(self, job_id: str) -> Any:
        return await self._client.get(f"/jobs/{job_id}")

    async def reports(self, status: str | None, season: str | None) -> Any:
        return await self._client.get("/reports/weekly/list", status=status, season=season)

    async def report(self, season: str, matchweek: int) -> Any:
        return await self._client.get(f"/reports/weekly/{season}/{matchweek}")

    # -- actions (triggered_by / edited_by always set here, never by the web) ---

    async def run_ingest(self, scope: str, triggered_by: str) -> Any:
        return await self._client.post(
            "/ingest/run", {"scope": scope, "triggered_by": triggered_by}
        )

    async def run_weekly_report(
        self, season: str | None, matchweek: int | None, triggered_by: str
    ) -> Any:
        body = {"season": season, "matchweek": matchweek, "triggered_by": triggered_by}
        return await self._client.post(
            "/reports/weekly/run", {k: v for k, v in body.items() if v is not None}
        )

    async def edit_report(
        self, season: str, matchweek: int, changes: dict[str, Any], edited_by: str
    ) -> Any:
        return await self._client.patch(
            f"/reports/weekly/{season}/{matchweek}", {**changes, "edited_by": edited_by}
        )

    async def publish_report(self, season: str, matchweek: int, actor: str) -> Any:
        return await self._client.post(
            f"/reports/weekly/{season}/{matchweek}/publish", {"published_by": actor}
        )

    async def unpublish_report(self, season: str, matchweek: int, actor: str) -> Any:
        return await self._client.post(
            f"/reports/weekly/{season}/{matchweek}/unpublish", {"unpublished_by": actor}
        )


def router_context(status: dict[str, Any] | None) -> dict[str, Any]:
    """`context` for RouteRequest; falls back to the calendar when 07 is down."""
    now = bangkok_now()
    status = status or {}
    return {
        "season": str(status.get("current_season") or season_for(now)),
        "current_matchweek": status.get("current_matchweek"),
        "now": now.isoformat(timespec="seconds"),
        "last_ingest_at": status.get("last_ingest_at"),
    }


class RetrievalAdminClient:
    def __init__(self, client: ServiceClient) -> None:
        self._client = client

    async def stats(self) -> Any:
        return await self._client.get("/index/stats")

    async def delete_document(self, doc_id: str) -> Any:
        return await self._client.delete(f"/index/{doc_id}")

    async def rebuild(self, request_id: str, category: str | None) -> Any:
        body: dict[str, Any] = {"request_id": request_id}
        if category:
            body["category"] = category
        return await self._client.post("/index/rebuild", body)
