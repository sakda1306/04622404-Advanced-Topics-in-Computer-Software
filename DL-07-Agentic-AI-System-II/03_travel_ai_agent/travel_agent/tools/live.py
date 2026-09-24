"""In-process adapters for the real Module 04, Module 05, and Module 06 implementations.

These modules currently expose Python functions/classes rather than HTTP services. This
adapter runs their blocking provider calls in worker threads and validates the evidence
that Module 03 sends onward. Weather (Open-Meteo) and routing (OSRM) need no API key;
transport (TomTom) degrades to "unavailable" without one.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from travel_agent.contracts import RiskLevel
from travel_agent.tools.base import ToolError
from travel_agent.tools.mocks import MockToolSet
from travel_agent.tools.schemas import (
    Alert,
    DisasterResult,
    IntegratedContext,
    KnowledgeResult,
    Record,
    RiskResult,
    RouteCandidate,
    RouteCandidatesResult,
    RouteResult,
    TransportResult,
    TravelQuery,
    WeatherResult,
)

CanonicalRecord = dict[str, Any]
TransportFetcher = Callable[..., list[CanonicalRecord]]
DisasterFetcher = Callable[..., list[CanonicalRecord]]
ContextBuilder = Callable[..., dict[str, Any]]
RiskKnowledgeFactory = Callable[..., Any]

_SOURCE_ROOT = Path(__file__).resolve().parents[3]
_IMAGE_ROOT = Path(__file__).resolve().parents[2]


def _dependency_path(directory: str, filename: str) -> Path:
    for root in (_SOURCE_ROOT, _IMAGE_ROOT):
        candidate = root / directory / filename
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"cannot find {directory}/{filename}")


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_package(name: str, directory: Path) -> ModuleType:
    """Load an adjacent package without requiring the monorepo to be installed."""
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    init_path = directory / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        name,
        init_path,
        submodule_search_locations=[str(directory)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load package {directory}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


WeatherCurrentFetcher = Callable[[float, float], CanonicalRecord]
WeatherForecastFetcher = Callable[[float, float], list[CanonicalRecord]]
RouteFetcher = Callable[..., list[dict[str, Any]]]


def _dependencies(transport_provider: str = "tomtom") -> tuple[
    TransportFetcher,
    DisasterFetcher,
    ContextBuilder,
    RiskKnowledgeFactory,
    WeatherCurrentFetcher,
    WeatherForecastFetcher,
    RouteFetcher,
]:
    transport_file = (
        "longdo_traffic_adapter.py"
        if transport_provider.lower() == "longdo"
        else "tomtom_transport.py"
    )
    transport = _load_module(
        "teamd_module04_transport",
        _dependency_path("04_external_data_services", transport_file),
    )
    disaster = _load_module(
        "teamd_module04_disaster",
        _dependency_path("04_external_data_services", "gdacs_adapter.py"),
    )
    integration = _load_module(
        "teamd_module05_integration",
        _dependency_path("05_data_integration", "integration.py"),
    )
    risk_knowledge = _load_package(
        "teamd_module06_risk_knowledge",
        _dependency_path("06_risk_knowledge_services", "risk_knowledge/__init__.py").parent,
    )
    weather_path = _dependency_path("04_external_data_services", "weather_service.py")
    if str(weather_path.parent) not in sys.path:
        sys.path.insert(0, str(weather_path.parent))
    weather = _load_module(
        "teamd_module04_weather",
        weather_path,
    )
    routes = _load_module(
        "teamd_module04_routes",
        _dependency_path("04_external_data_services", "route_candidates.py"),
    )
    return (
        transport.fetch_canonical_transport,
        disaster.fetch_canonical_disasters,
        integration.build_context,
        risk_knowledge.RiskKnowledgeService,
        weather.fetch_canonical_current_weather,
        weather.fetch_canonical_forecast,
        routes.fetch_route_candidates,
    )


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _source_url(record: CanonicalRecord) -> str:
    value = record.get("source_lineage")
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ValueError("available canonical record needs HTTPS source_lineage")
    return value


def _evidence_record(record: CanonicalRecord, *, kind: str) -> Record:
    fetched_at = _aware(record.get("fetched_at"))
    expires_at = _aware(record.get("expires_at"))
    if fetched_at is None or expires_at is None:
        raise ValueError("canonical record needs fetched_at and expires_at")
    value = record.get("value")
    time_validity = (
        value.get("time_validity")
        if isinstance(value, dict)
        else record.get("time_validity")
    )
    # When an incident is active/ongoing (time_validity: present), the live query verified
    # its presence at fetched_at. Use fetched_at as the observation time so long-running
    # closures/incidents do not falsely appear stale based on an old event start time.
    if isinstance(time_validity, str) and time_validity.lower() == "present":
        observed_at = fetched_at
    else:
        # This is the time Module 03 actually observed the provider record. Prefer the
        # source event/report time when it is usable, but never invent a future observation.
        observed_at = next(
            (
                v
                for field in ("observed_at", "event_time", "issued_at")
                if (v := _aware(record.get(field))) is not None and v <= fetched_at
            ),
            fetched_at,
        )
    source = record.get("source")
    source_name = source.get("name") if isinstance(source, dict) else None
    if not isinstance(source_name, str) or not source_name:
        raise ValueError("canonical record needs source.name")
    description = value.get("description") if isinstance(value, dict) else None
    excerpt = (
        description
        if isinstance(description, str) and description
        else str(record.get("record_kind", "external data"))
    )
    return Record(
        kind=kind,
        source_name=source_name,
        url=_source_url(record),
        official_source=False,
        observed_at=observed_at,
        fetched_at=fetched_at,
        expires_at=expires_at,
        excerpt=excerpt[:4000],
    )


def _check_record(*, kind: str, source_name: str, url: str, now: datetime) -> Record:
    return Record(
        kind=kind,
        source_name=source_name,
        url=url,
        official_source=False,
        observed_at=now,
        fetched_at=now,
        expires_at=now + timedelta(minutes=5),
        excerpt="Provider check completed and returned no matching active records.",
    )


def _bbox(query: TravelQuery) -> tuple[float, float, float, float]:
    origin_lat, origin_lon = query.origin
    destination_lat, destination_lon = query.destination
    west, east = sorted((origin_lon, destination_lon))
    south, north = sorted((origin_lat, destination_lat))
    # TomTom requires a non-zero rectangle. Padding only defines the query area; it
    # does not fabricate evidence or change the requested endpoints.
    if west == east:
        west, east = max(-180.0, west - 0.005), min(180.0, east + 0.005)
    if south == north:
        south, north = max(-90.0, south - 0.005), min(90.0, north + 0.005)
    return west, south, east, north


def _weather_citations(
    available: list[CanonicalRecord], departure: datetime
) -> list[CanonicalRecord]:
    """Pick the weather records 07 should cite; 05 still receives every record.

    Open-Meteo returns one forecast record per hour (48 per location), which would
    overflow 07's 64-item evidence limit. Cite current weather plus, per location, the
    first forecast hour at or after departure (or the last hour if all are earlier).
    """
    cited = [r for r in available if r.get("record_kind") == "current_weather"]
    by_location: dict[str, list[tuple[datetime, CanonicalRecord]]] = {}
    for record in available:
        valid_at = _aware(record.get("valid_at"))
        if record.get("record_kind") != "weather_forecast" or valid_at is None:
            continue
        footprint = record.get("spatial_footprint") or {}
        key = str(footprint.get("coordinates"))
        by_location.setdefault(key, []).append((valid_at, record))
    for hours in by_location.values():
        hours.sort(key=lambda item: item[0])
        upcoming = [record for valid_at, record in hours if valid_at >= departure]
        cited.append(upcoming[0] if upcoming else hours[-1][1])
    return cited


def _available(records: list[CanonicalRecord], tool: str) -> list[CanonicalRecord]:
    available = [record for record in records if record.get("status") == "available"]
    if available:
        return available
    unavailable = next(
        (record for record in records if record.get("status") == "unavailable"), None
    )
    if unavailable is not None:
        raise ToolError(tool, str(unavailable.get("error_code") or "provider unavailable"))
    return []


class LiveToolSet(MockToolSet):
    """Use real 04 (weather/transport/disaster/routing), 05 integration, and 06 risk."""

    def __init__(
        self,
        *,
        transport_provider: str = "tomtom",
        longdo_api_key: str | None = None,
        tomtom_api_key: str | None = None,
        osrm_base_url: str = "https://router.project-osrm.org",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        transport_fetcher: TransportFetcher | None = None,
        disaster_fetcher: DisasterFetcher | None = None,
        context_builder: ContextBuilder | None = None,
        risk_knowledge_service: Any | None = None,
        current_weather_fetcher: WeatherCurrentFetcher | None = None,
        forecast_fetcher: WeatherForecastFetcher | None = None,
        route_fetcher: RouteFetcher | None = None,
    ) -> None:
        super().__init__(clock)
        defaults = None
        if any(
            x is None
            for x in (
                transport_fetcher,
                disaster_fetcher,
                context_builder,
                risk_knowledge_service,
                current_weather_fetcher,
                forecast_fetcher,
                route_fetcher,
            )
        ):
            defaults = _dependencies(transport_provider=transport_provider)

        self._transport_provider = transport_provider.lower()
        self._longdo_api_key = longdo_api_key
        self._tomtom_api_key = tomtom_api_key
        # No API key required: OSRM's public demo server has no auth, but it is rate
        # limited and unsuitable for production load; point this at a self-hosted
        # instance for real deployments.
        self._osrm_base_url = osrm_base_url
        self._fetch_transport = transport_fetcher or (defaults[0] if defaults else None)
        self._fetch_disasters = disaster_fetcher or (defaults[1] if defaults else None)
        self._build_context = context_builder or (defaults[2] if defaults else None)
        self._risk_knowledge = risk_knowledge_service or (
            defaults[3](clock=clock) if defaults else None
        )
        self._fetch_current_weather = current_weather_fetcher or (defaults[4] if defaults else None)
        self._fetch_forecast = forecast_fetcher or (defaults[5] if defaults else None)
        self._fetch_routes = route_fetcher or (defaults[6] if defaults else None)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    async def weather(self, query: TravelQuery) -> WeatherResult:
        now = self._now()
        lon_a, lat_a = query.origin[1], query.origin[0]
        lon_b, lat_b = query.destination[1], query.destination[0]
        canonical = []
        try:
            # Module 04's weather entry points take (latitude, longitude) only.
            for lat, lon in ((lat_a, lon_a), (lat_b, lon_b)):
                curr = await asyncio.to_thread(self._fetch_current_weather, lat, lon)
                if curr:
                    canonical.append(curr)
                fore = await asyncio.to_thread(self._fetch_forecast, lat, lon)
                if fore:
                    canonical.extend(fore)
        except Exception as error:
            raise ToolError("weather", f"invalid Module 04 result: {error}") from error

        available = _available(canonical, "weather")
        departure = query.departure_time.astimezone(UTC)
        try:
            evidence = [
                _evidence_record(record, kind="weather")
                for record in _weather_citations(available, departure)
            ]
        except Exception as error:
            raise ToolError("weather", f"invalid Module 04 result: {error}") from error
        evidence = evidence or [
            _check_record(
                kind="weather",
                source_name="Open-Meteo Weather API",
                url="https://api.open-meteo.com/v1/forecast",
                now=now,
            )
        ]
        return WeatherResult(
            summary=f"Open-Meteo returned {len(available)} weather record(s).",
            records=evidence,
            canonical_records=canonical,
        )

    async def transport(self, query: TravelQuery) -> TransportResult:
        now = self._now()
        api_key = (
            self._longdo_api_key
            if self._transport_provider == "longdo"
            else self._tomtom_api_key
        )
        try:
            canonical = await asyncio.to_thread(
                self._fetch_transport,
                _bbox(query),
                now=now,
                api_key=api_key,
            )
            available = _available(canonical, "transport")
            fallback_source = (
                "Longdo Traffic (iTIC)"
                if self._transport_provider == "longdo"
                else "TomTom Orbis Traffic"
            )
            fallback_url = (
                "https://event.longdo.com/feed/json"
                if self._transport_provider == "longdo"
                else "https://api.tomtom.com/maps/orbis/traffic/incidents/details"
            )
            evidence = [_evidence_record(record, kind="transport") for record in available] or [
                _check_record(
                    kind="transport",
                    source_name=fallback_source,
                    url=fallback_url,
                    now=now,
                )
            ]
        except ToolError:
            raise
        except Exception as error:
            raise ToolError("transport", f"invalid Module 04 result: {error}") from error
        count = len(available)
        provider_name = (
            "Longdo Traffic (iTIC)"
            if self._transport_provider == "longdo"
            else "TomTom"
        )
        return TransportResult(
            summary=f"{provider_name} returned {count} active transport incident(s).",
            records=evidence,
            canonical_records=canonical,
        )

    async def disasters(self, query: TravelQuery) -> DisasterResult:
        now = self._now()
        try:
            canonical = await asyncio.to_thread(self._fetch_disasters, now=now)
            available = _available(canonical, "disasters")
            evidence = [_evidence_record(record, kind="official") for record in available] or [
                _check_record(
                    kind="official",
                    source_name="Global Disaster Alert and Coordination System, GDACS",
                    url="https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH",
                    now=now,
                )
            ]
            alerts = (
                [
                    self._alert(record, proof, now)
                    for record, proof in zip(available, evidence, strict=True)
                ]
                if available
                else []
            )
        except ToolError:
            raise
        except Exception as error:
            raise ToolError("disasters", f"invalid Module 04 result: {error}") from error
        return DisasterResult(
            alerts=alerts[:20],
            records=evidence,
            canonical_records=canonical,
        )

    @staticmethod
    def _alert(record: CanonicalRecord, proof: Record, now: datetime) -> Alert:
        value = record.get("value") if isinstance(record.get("value"), dict) else {}
        starts_at = _aware(value.get("starts_at"))
        ends_at = _aware(value.get("ends_at"))
        active = starts_at is not None and starts_at <= now and (ends_at is None or now <= ends_at)
        severity = {
            "LOW": RiskLevel.LOW,
            "MEDIUM": RiskLevel.MEDIUM,
            "HIGH": RiskLevel.HIGH,
        }.get(record.get("severity"), RiskLevel.MEDIUM)
        title = value.get("name")
        if not isinstance(title, str) or not title:
            title = f"GDACS {value.get('event_type') or 'disaster'} event"
        return Alert(
            hazard_id=str(record["record_id"]),
            hazard_type=str(value.get("event_type") or "DISASTER"),
            severity=severity,
            # GDACS is hazard evidence, not a Thai closure order. Module 07 decides.
            level="CAUTION",
            active=active,
            starts_at=starts_at,
            ends_at=ends_at,
            title=title[:300],
            record=proof,
        )

    async def integrate(
        self,
        query: TravelQuery,
        routes: list[dict],
        weather,
        transport: TransportResult | None,
        disasters: DisasterResult | None,
    ) -> IntegratedContext:
        canonical = [
            record
            for result in (weather, transport, disasters)
            if result is not None and hasattr(result, "canonical_records")
            for record in result.canonical_records
        ]
        try:
            context = await asyncio.to_thread(
                self._build_context,
                {"run_id": query.run_id, "routes": routes},
                canonical,
                now=self._now(),
            )
            return IntegratedContext.model_validate(context)
        except Exception as error:
            raise ToolError("integrate", f"invalid Module 05 result: {error}") from error

    async def risk(self, query: TravelQuery, context: IntegratedContext | None) -> RiskResult:
        try:
            result = await self._risk_knowledge.risk(
                query.model_dump(mode="python"),
                context.model_dump(mode="python") if context is not None else None,
            )
            return RiskResult.model_validate(result.model_dump(mode="python"))
        except Exception as error:
            raise ToolError("risk", f"invalid Module 06 result: {error}") from error

    async def knowledge(self, query: TravelQuery, alerts: list[Alert]) -> KnowledgeResult:
        try:
            result = await self._risk_knowledge.knowledge(
                query.model_dump(mode="python"),
                [alert.model_dump(mode="python") for alert in alerts],
            )
            return KnowledgeResult.model_validate(result.model_dump(mode="python"))
        except Exception as error:
            raise ToolError("knowledge", f"invalid Module 06 result: {error}") from error

    async def routes(
        self,
        query: TravelQuery,
        context: IntegratedContext | None,
        risk: RiskResult | None,
    ) -> RouteResult:
        try:
            result = await self._risk_knowledge.routes(
                query.model_dump(mode="python"),
                context.model_dump(mode="python") if context is not None else None,
                risk.model_dump(mode="python") if risk is not None else None,
            )
            return RouteResult.model_validate(result.model_dump(mode="python"))
        except Exception as error:
            raise ToolError("routes", f"invalid Module 06 result: {error}") from error

    async def route_candidates(self, query: TravelQuery) -> RouteCandidatesResult:
        now = self._now()
        try:
            raw = await asyncio.to_thread(
                self._fetch_routes,
                query.origin,
                query.destination,
                base_url=self._osrm_base_url,
            )
            candidates = [RouteCandidate.model_validate(candidate) for candidate in raw]
        except ToolError:
            raise
        except Exception as error:
            raise ToolError("route_candidates", f"invalid Module 04 result: {error}") from error
        evidence = [
            _check_record(
                kind="route",
                source_name="OSRM routing",
                url=f"{self._osrm_base_url}/route/v1/driving",
                now=now,
            )
        ]
        return RouteCandidatesResult(candidates=candidates, records=evidence)
